"""CSV → mass build orchestrator.

Reads a CSV of prospects, runs build_one per row, with:
  - asyncio Semaphore for bounded concurrency (default 5)
  - Idempotency: skip already-rendered slugs
  - Hard budget cap: stops the run when total LLM cost exceeds MAX_BUDGET_USD
  - Resilient to crashes: re-runs claim stale 'building' rows

Each worker uses its own LLM client (so cost tracking aggregates correctly).
"""

from __future__ import annotations

import asyncio
import csv
import re
from pathlib import Path
from typing import Iterable

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from .builder import BuildResult, build_one
from .config import CONFIG
from .db import BuildsRepo
from .llm import LLM
from .models import ProspectInput

console = Console()


# ---------- CSV ingestion ---------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Stable, lowercase, dash-separated slug. ASCII-safe."""
    import unicodedata
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = _SLUG_RE.sub("-", norm.lower()).strip("-")
    return s or "prospect"


def parse_csv(path: Path) -> list[ProspectInput]:
    """Read a CSV. Required: company_name. Optional: slug, source_text,
    sector_hint, phone, phone_tel, email, hero_image_url."""
    prospects: list[ProspectInput] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            name = (row.get("company_name") or "").strip()
            if not name:
                console.print(f"[yellow]Skip line {i}: missing company_name[/]")
                continue
            slug = (row.get("slug") or "").strip() or slugify(name)
            prospects.append(ProspectInput(
                slug=slug,
                company_name=name,
                source_text=(row.get("source_text") or "").strip(),
                sector_hint=(row.get("sector_hint") or "").strip() or None,
                phone=(row.get("phone") or "").strip() or None,
                phone_tel=(row.get("phone_tel") or "").strip() or None,
                email=(row.get("email") or "").strip() or None,
                hero_image_url=(row.get("hero_image_url") or "").strip() or None,
            ))
    return prospects


# ---------- Async orchestrator ----------------------------------------------

async def _build_async(prospect: ProspectInput, repo: BuildsRepo, llm: LLM,
                       dry_run: bool) -> BuildResult:
    # build_one is sync; offload to a thread so we get real concurrency
    return await asyncio.to_thread(build_one, prospect, repo, llm, dry_run)


async def build_all_async(prospects: Iterable[ProspectInput],
                          max_concurrency: int | None = None,
                          max_budget_usd: float | None = None,
                          dry_run: bool = False) -> list[BuildResult]:
    repo = BuildsRepo()
    sem = asyncio.Semaphore(max_concurrency or CONFIG.max_concurrency)
    budget = max_budget_usd if max_budget_usd is not None else CONFIG.max_budget_usd

    # Pre-register all prospects as pending (so the DB shows the intended scope)
    prospects_list = list(prospects)
    for p in prospects_list:
        repo.upsert_pending(p.slug, p.company_name)

    # Skip the ones already rendered
    todo = [p for p in prospects_list if not repo.is_done(p.slug)]
    skipped = len(prospects_list) - len(todo)
    if skipped:
        console.print(f"[dim]Skipping {skipped} already-rendered slugs.[/]")

    results: list[BuildResult] = []
    stop_flag = {"stop": False}
    llm = LLM()  # Shared cost counter across all workers in this run

    async def worker(p: ProspectInput) -> BuildResult:
        async with sem:
            # Check BEFORE the call to bound overshoot to (concurrency × cost_per_call)
            # instead of unbounded N×concurrency simultaneous fires.
            current_cost = llm.usage.cost_snapshot()
            if stop_flag["stop"] or current_cost >= budget:
                if not stop_flag["stop"]:
                    stop_flag["stop"] = True
                    console.print(f"[red bold]Budget cap reached "
                                  f"(${current_cost:.4f} ≥ ${budget}). Stopping.[/]")
                return BuildResult(slug=p.slug, ok=False, error="budget-cap-stop")
            res = await _build_async(p, repo, llm, dry_run)
            # Re-check after, in case this single call pushed us over
            if llm.usage.cost_snapshot() >= budget:
                if not stop_flag["stop"]:
                    stop_flag["stop"] = True
                    console.print(f"[red bold]Budget cap reached after call "
                                  f"(${llm.usage.cost_snapshot():.4f} ≥ ${budget}). Stopping.[/]")
            return res

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Building", total=len(todo))
        coros = [worker(p) for p in todo]
        for fut in asyncio.as_completed(coros):
            res = await fut
            results.append(res)
            progress.advance(task)

    # Summary
    ok = sum(1 for r in results if r.ok)
    failed = sum(1 for r in results if not r.ok)
    console.print(f"\n[bold]Done.[/] ok={ok} failed={failed} "
                  f"total_cost=${llm.usage.cost_snapshot():.4f} calls={llm.usage.calls}")
    return results


def build_all_sync(*args, **kwargs) -> list[BuildResult]:
    """Synchronous entrypoint, just wraps build_all_async in asyncio.run."""
    return asyncio.run(build_all_async(*args, **kwargs))
