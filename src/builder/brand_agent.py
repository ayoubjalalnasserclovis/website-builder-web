"""Brand DNA agent — produces a unique visual identity for each website.

This is what kills the "every site looks the same" problem. The agent reads:
  - skills/design_director.md   (the playbook — non-negotiable principles + sector rules)
  - the company brief           (name + source text + sector)

And outputs a BrandDNA: palette, typography pair, mood, layout variant.
The renderer then converts that DNA into CSS variables and a dynamic
Google Fonts URL — the same template skeleton can yield visually distinct
sites without duplicating HTML.

Why a skill .md file and not a hardcoded prompt:
  - Easier to iterate on design quality (edit text, no code change)
  - The skill is human-reviewable, version-controlled, copyable to other projects
  - LLM behavior is dictated by a *document*, not a black-box function
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
from rich.console import Console

from .config import CONFIG
from .llm import LLM, parse_json_robust
from .models import BrandDNA, ProspectInput

console = Console()

MAX_RETRIES = 2

DEFAULT_SKILL_PATH = Path(__file__).resolve().parents[2] / "skills" / "design_director.md"


def _load_skill(path: Path | None = None) -> str:
    skill_path = path or DEFAULT_SKILL_PATH
    if not skill_path.exists():
        raise FileNotFoundError(
            f"Design director skill not found at {skill_path}. "
            f"Expected skills/design_director.md at the repo root."
        )
    return skill_path.read_text(encoding="utf-8")


def _build_user_prompt(prospect: ProspectInput) -> str:
    sector = prospect.sector_hint or "à déduire du texte"
    return f"""\
Brief :

ENTREPRISE : {prospect.company_name}
SECTEUR : {sector}

TEXTE SOURCE (peut être incomplet) :
---
{prospect.source_text or "(rien fourni — déduis tout du nom et du secteur)"}
---

Produis l'ADN visuel de ce site, suivant strictement la grille de la skill.
Réponds UNIQUEMENT avec du JSON valide, sans markdown, sans préambule.
"""


class BrandAgent:
    """Produces a BrandDNA from a ProspectInput, with validation retries."""

    def __init__(self, llm: LLM | None = None, skill_path: Path | None = None):
        # Reuse the content LLM (Haiku-class is fine — JSON output, no vision needed)
        self.llm = llm or LLM(model=CONFIG.model_content,
                              fallback=CONFIG.model_content_fallback)
        self.skill = _load_skill(skill_path)

    def generate(self, prospect: ProspectInput) -> BrandDNA:
        last_error: str | None = None
        last_raw: str | None = None

        for attempt in range(MAX_RETRIES + 1):
            user = _build_user_prompt(prospect)
            if last_error:
                user += (
                    f"\n\n--- TENTATIVE PRÉCÉDENTE INVALIDE ---\n"
                    f"Tu as produit ce JSON :\n{last_raw[:1500] if last_raw else ''}\n\n"
                    f"Erreurs :\n{last_error}\n\n"
                    f"Corrige UNIQUEMENT les champs problématiques, reproduis le JSON COMPLET corrigé."
                )

            raw = self.llm.complete_json(self.skill, user, temperature=0.85)
            last_raw = raw

            try:
                data = parse_json_robust(raw)
            except ValueError as e:
                last_error = str(e)
                console.print(f"[yellow]BrandAgent attempt {attempt+1}: invalid JSON, retrying...[/]")
                continue

            try:
                return BrandDNA.model_validate(data)
            except ValidationError as e:
                last_error = e.json(indent=2)
                console.print(f"[yellow]BrandAgent attempt {attempt+1}: validation failed, retrying...[/]")
                continue

        raise RuntimeError(
            f"BrandDNA generation failed after {MAX_RETRIES + 1} attempts.\n"
            f"Last error:\n{last_error}"
        )


# --- Default fallback (used when the agent isn't wired in, e.g. legacy tests) ---

DEFAULT_BRAND_DNA = BrandDNA(
    palette={
        "bg":        "#F6F2EB",
        "surface":   "#ECE6DA",
        "text":      "#15151A",
        "primary":   "#14213D",
        "secondary": "#C9A66B",
    },
    typography={"display_font": "Fraunces", "body_font": "Inter"},
    mood="refined",
    layout_variant="editorial_classic",
    rationale="Palette navy/crème/or, typographie sérif éditoriale — convient au standard banque privée.",
)
