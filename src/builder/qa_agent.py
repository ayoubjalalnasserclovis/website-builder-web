"""QA agent — visually audits a built site before deploy.

Pipeline per prospect:
  1. Open dist/<slug>/index.html in headless Chromium
  2. Full-page screenshot → qa_screenshots/<slug>.jpg
  3. Send screenshot + structured prompt to vision LLM (Gemini 2.5 Flash by default)
  4. Parse + validate the response as QAReport (retry once on validation error)
  5. Apply business rule: pass iff score ≥ threshold AND no 'critical' findings
  6. Update DB: status → qa_passed | qa_rejected, persist score + findings + screenshot path

The verdict from the LLM is treated as advisory; the *final* pass/reject is
re-derived from score + findings to ensure the business rule is enforced even
if the LLM is sloppy.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import ValidationError
from rich.console import Console

from .config import CONFIG
from .db import BuildRow, BuildsRepo
from .llm import LLM, parse_json_robust
from .models import QAReport
from .screenshot import Browser, shared_browser

console = Console()

MAX_RETRIES = 1


# --- Prompt -----------------------------------------------------------------

SYSTEM_PROMPT = """\
Tu es directeur artistique chez une agence parisienne de design éditorial.
Tu audites la qualité visuelle de sites web pour PME françaises, sur le
standard "banque privée" (référence : Edmond de Rothschild, J.P. Morgan
Private Bank, Hermès — typographie premium, beaucoup d'espace, palette sobre).

Tu produis un audit STRICT et HONNÊTE. Tu ne flattes pas. Si le site est moyen,
tu mets 5. Si excellent, tu mets 9 ou 10. Le 7 est la barre minimum acceptable
pour envoyer à un prospect.

GRILLE DE NOTATION (sur 10) :
- 10  : impeccable, signé Hermès, prêt à publier
-  9  : très bon, juste 1-2 détails de polish
-  8  : bon, accrocs mineurs sans gravité
-  7  : acceptable, sortable mais pas fier
-  5-6: moyen, problèmes notables (à corriger)
- < 5 : à refaire entièrement

CRITÈRES DE VÉRIFICATION (audite chacun) :
- typography : lisibilité, hiérarchie, italique appliqué quand il devrait, pas de chevauchement
- layout    : pas de bloc vide, pas de débordement, alignements propres, respiration
- image     : hero image présente et chargée (pas de zone grise/cassée), pas d'icône moche
- content   : français correct, pas de "lorem ipsum", pas de placeholder type "<...>"
- language  : qualité du français (pas d'anglicisme, pas de syntaxe LLM bancale)
- consistency : palette respectée, ton uniforme, brand mark présent

SÉVÉRITÉ DES FINDINGS :
- critical : bloque l'envoi (image cassée, texte placeholder, débordement majeur)
- minor    : à corriger mais pas bloquant
- polish   : nice-to-have, n'empêche pas le pass

TU PRODUIS UNIQUEMENT DU JSON STRICT, sans markdown, sans préambule.
"""

USER_TEMPLATE = """\
Voici un site web généré pour cette entreprise française.

ENTREPRISE : {company_name}
SECTEUR : {sector}

Évalue la qualité visuelle. Réponds avec EXACTEMENT cette structure JSON :

{{
  "score": <entier 0-10>,
  "verdict": "pass" | "reject",
  "summary": "<1-2 phrases en français, ce qui marche / ce qui cloche>",
  "findings": [
    {{
      "severity": "critical" | "minor" | "polish",
      "area": "typography" | "layout" | "image" | "content" | "language" | "consistency",
      "description": "<observation précise et localisée>"
    }}
  ]
}}

Règle d'or : verdict = "pass" UNIQUEMENT si score >= {threshold} ET aucune
finding "critical". Sinon verdict = "reject".
"""


# --- Result dataclass -------------------------------------------------------

@dataclass
class QAResult:
    slug: str
    ok: bool
    score: Optional[int] = None
    verdict: Optional[str] = None       # final pass/reject (after enforcement)
    findings_count: int = 0
    screenshot_path: Optional[str] = None
    error: Optional[str] = None


# --- Business rule ----------------------------------------------------------

def _enforce_verdict(report: QAReport, threshold: int) -> str:
    """Re-derive pass/reject from score + findings. Don't trust the LLM's verdict alone."""
    has_critical = any(f.severity == "critical" for f in report.findings)
    if report.score >= threshold and not has_critical:
        return "pass"
    return "reject"


# --- Agent ------------------------------------------------------------------

class QAAgent:
    def __init__(self, llm: LLM | None = None, threshold: int | None = None,
                 screenshots_dir: Path | None = None):
        # We use the QA-specific model. The same LLM instance shares its cost tracker
        # with content generation (so total budget cap remains coherent).
        self.llm = llm or LLM(model=CONFIG.model_qa, fallback=CONFIG.model_qa)
        self.threshold = threshold if threshold is not None else CONFIG.qa_score_threshold
        self.screenshots_dir = screenshots_dir or CONFIG.qa_screenshots_dir

    async def review(self, build: BuildRow, browser: Browser,
                     repo: BuildsRepo | None = None) -> QAResult:
        repo = repo or BuildsRepo()

        if not build.html_path:
            return QAResult(slug=build.slug, ok=False, error="no html_path on build row")
        html_path = Path(build.html_path)
        if not html_path.exists():
            return QAResult(slug=build.slug, ok=False,
                            error=f"html_path does not exist: {html_path}")

        # 1. Screenshot
        screenshot_path = self.screenshots_dir / f"{build.slug}.jpg"
        try:
            await browser.screenshot(html_path, screenshot_path)
        except Exception as e:
            err = f"screenshot failed: {e}"
            console.print(f"[red]✗ {build.slug}: {err}[/]")
            return QAResult(slug=build.slug, ok=False, error=err)

        # 2-4. Vision LLM with retry on validation error
        sector = "non spécifié"
        try:
            content_data = json.loads(build.content_json) if build.content_json else {}
            sector = content_data.get("sector") or sector
        except (json.JSONDecodeError, TypeError):
            pass

        report = await asyncio.to_thread(
            self._score_screenshot,
            company_name=build.company_name,
            sector=sector,
            screenshot_path=screenshot_path,
        )

        if report is None:
            err = "vision LLM did not return a valid QAReport after retries"
            console.print(f"[red]✗ {build.slug}: {err}[/]")
            return QAResult(slug=build.slug, ok=False,
                            screenshot_path=str(screenshot_path), error=err)

        # 5. Enforce business rule (don't trust LLM verdict blindly)
        final_verdict = _enforce_verdict(report, self.threshold)

        # 6. Persist
        findings_json = json.dumps([f.model_dump() for f in report.findings],
                                   ensure_ascii=False)
        repo.record_qa_result(
            slug=build.slug,
            score=report.score,
            verdict=final_verdict,
            findings_json=findings_json,
            screenshot_path=str(screenshot_path),
        )

        verdict_color = "green" if final_verdict == "pass" else "yellow"
        console.print(
            f"[{verdict_color}]{'✓' if final_verdict == 'pass' else '⚠'}[/] "
            f"{build.slug}: score [bold]{report.score}/10[/] → {final_verdict} "
            f"({len(report.findings)} findings)"
        )
        return QAResult(
            slug=build.slug, ok=True,
            score=report.score, verdict=final_verdict,
            findings_count=len(report.findings),
            screenshot_path=str(screenshot_path),
        )

    def _score_screenshot(self, company_name: str, sector: str,
                          screenshot_path: Path) -> QAReport | None:
        """Sync wrapper around the vision LLM call (offloaded via asyncio.to_thread)."""
        user_text = USER_TEMPLATE.format(
            company_name=company_name,
            sector=sector,
            threshold=self.threshold,
        )

        last_error: str | None = None
        for attempt in range(MAX_RETRIES + 1):
            prompt = user_text
            if last_error:
                prompt += (
                    f"\n\n--- TENTATIVE PRÉCÉDENTE INVALIDE ---\n"
                    f"{last_error}\nReproduis le JSON COMPLET corrigé."
                )

            try:
                raw = self.llm.vision_json(
                    model=self.llm.model,
                    system=SYSTEM_PROMPT,
                    user_text=prompt,
                    image_path=screenshot_path,
                )
            except Exception as e:
                last_error = f"LLM call failed: {e}"
                continue

            try:
                data = parse_json_robust(raw)
            except ValueError as e:
                last_error = str(e)
                continue

            try:
                return QAReport.model_validate(data)
            except ValidationError as e:
                last_error = e.json(indent=2)
                continue

        return None


# --- Batch entry point ------------------------------------------------------

async def review_batch(repo: BuildsRepo | None = None,
                       only_slug: str | None = None) -> list[QAResult]:
    """Run QA on all `rendered` and `qa_rejected` rows in DB. Sequential per-page,
    bounded by QA_CONCURRENCY in the screenshot helper."""
    repo = repo or BuildsRepo()

    if only_slug:
        row = repo.get(only_slug)
        if not row:
            console.print(f"[red]No build with slug '{only_slug}'[/]")
            return []
        if not row.html_path:
            console.print(f"[red]Build '{only_slug}' has no html_path[/]")
            return []
        targets: list[BuildRow] = [row]
    else:
        targets = repo.list_for_qa()

    if not targets:
        console.print("[dim]No sites to QA.[/]")
        return []

    console.print(f"[bold]QA pass on {len(targets)} sites[/]")

    agent = QAAgent()
    results: list[QAResult] = []

    async with shared_browser() as browser:
        coros = [agent.review(b, browser, repo) for b in targets]
        for fut in asyncio.as_completed(coros):
            results.append(await fut)

    passed = sum(1 for r in results if r.verdict == "pass")
    rejected = sum(1 for r in results if r.verdict == "reject")
    errored = sum(1 for r in results if not r.ok)
    console.print(
        f"\n[bold]Done.[/] passed={passed} rejected={rejected} "
        f"errored={errored} cost=${agent.llm.usage.cost_snapshot():.4f}"
    )
    return results


def review_batch_sync(only_slug: str | None = None) -> list[QAResult]:
    return asyncio.run(review_batch(only_slug=only_slug))
