"""Single-prospect builder. The unit of work for the batch orchestrator.

Flow:
  1. Claim the slug in DB (atomic)
  2. ContentAgent.generate() → SiteContent
  3. ImagePicker → hero_image_url
  4. Render to dist/<slug>/index.html
  5. Mark rendered in DB

Failures at any step → mark failed with the error string.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console

from .config import CONFIG
from .content_agent import ContentAgent
from .db import BuildsRepo
from .image_picker import pick_hero_image
from .llm import LLM
from .models import ProspectInput, SiteContent
from .render import render_to_disk

console = Console()


@dataclass
class BuildResult:
    slug: str
    ok: bool
    html_path: str | None = None
    error: str | None = None
    cost_usd: float = 0.0


def build_one(prospect: ProspectInput,
              repo: BuildsRepo | None = None,
              llm: LLM | None = None,
              dry_run: bool = False) -> BuildResult:
    repo = repo or BuildsRepo()
    llm = llm or LLM()
    agent = ContentAgent(llm=llm)

    # Ensure the slug exists in DB (idempotent)
    repo.upsert_pending(prospect.slug, prospect.company_name)

    # Try to claim
    if not repo.mark_building(prospect.slug):
        # Already done, or actively being built by another worker
        existing = repo.get(prospect.slug)
        if existing and existing.status == "rendered":
            return BuildResult(slug=prospect.slug, ok=True, html_path=existing.html_path)
        return BuildResult(
            slug=prospect.slug, ok=False,
            error="Could not claim slug (already building elsewhere or recently completed).",
        )

    cost_before = llm.usage.cost_usd

    try:
        # 1. Generate validated content
        if dry_run:
            console.print(f"[yellow][dry-run][/] would call LLM for {prospect.slug}")
            return BuildResult(slug=prospect.slug, ok=True)

        console.print(f"[cyan]→ Generating content for {prospect.slug}...[/]")
        content: SiteContent = agent.generate(prospect)

        # 2. Resolve hero image
        if prospect.hero_image_url:
            content.hero_image_url = prospect.hero_image_url
        else:
            content.hero_image_url = pick_hero_image(content.sector, content.slug)

        # 3. Render to disk
        html_path = render_to_disk(content)

        # 4. Compute LLM cost for this prospect
        cost_for_this = llm.usage.cost_usd - cost_before

        # 5. Persist
        repo.mark_rendered(
            slug=prospect.slug,
            content_json=content.model_dump_json(),
            html_path=str(html_path),
            llm_cost_usd=cost_for_this,
        )
        repo.record_llm_call(
            slug=prospect.slug,
            model=llm.model,
            input_tokens=llm.usage.input_tokens,
            output_tokens=llm.usage.output_tokens,
            cost_usd=cost_for_this,
        )

        console.print(f"[green]✓[/] {prospect.slug} → {html_path} (${cost_for_this:.4f})")
        return BuildResult(slug=prospect.slug, ok=True, html_path=str(html_path),
                           cost_usd=cost_for_this)

    except Exception as e:
        console.print(f"[red]✗ {prospect.slug}: {e}[/]")
        repo.mark_failed(prospect.slug, str(e))
        return BuildResult(slug=prospect.slug, ok=False, error=str(e))
