"""Cold email writer agent — produces a personalized B2B email per prospect.

Flow:
  1. Load skills/cold_email_writer.md (the playbook)
  2. Build the prompt with: prospect info + brand DNA mood + sender identity
     + demo URL + optional source_text from the prospect's existing site
  3. Call LLM with strict JSON output
  4. Validate against ColdEmail Pydantic model (which enforces RGPD —
     {{unsubscribe_link}} placeholder must be present)
  5. Retry once on validation error with feedback

Why a skill .md file (not a hardcoded prompt):
  - Easier to iterate on copy quality without code changes
  - Anti-spam rules + RGPD requirements + tone guidance live in one document
  - Reviewable by a human (legal team, marketing) without reading Python
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
from rich.console import Console

from .config import CONFIG
from .llm import LLM, parse_json_robust
from .models import BrandDNA, ColdEmail, ProspectInput, SenderIdentity, SiteContent

console = Console()

MAX_RETRIES = 2

DEFAULT_SKILL_PATH = Path(__file__).resolve().parents[2] / "skills" / "cold_email_writer.md"


def _load_skill(path: Path | None = None) -> str:
    p = path or DEFAULT_SKILL_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"Cold email skill not found at {p}. "
            f"Expected skills/cold_email_writer.md at the repo root."
        )
    return p.read_text(encoding="utf-8")


def _build_user_prompt(
    *,
    prospect: ProspectInput,
    content: SiteContent,
    brand: BrandDNA,
    sender: SenderIdentity,
    demo_url: str,
) -> str:
    # Try to identify a first name from the email or a fallback
    first_name_hint = ""
    if prospect.email and "." in prospect.email.split("@")[0]:
        # firstname.lastname@domain pattern
        first_part = prospect.email.split("@")[0].split(".")[0]
        first_name_hint = first_part.capitalize()

    # Pull a content hint from the site content (eg founder name, sector vibe)
    founder_name = ""
    try:
        founder_name = content.manifesto.founder_name or ""
    except Exception:
        pass

    return f"""\
Brief :

ENTREPRISE       : {prospect.company_name}
SECTEUR          : {prospect.sector_hint or content.sector or "?"}
EMAIL DESTINATAIRE: {prospect.email or "(inconnu — utilise une salutation générique)"}
PRÉNOM HINT      : {first_name_hint or "(aucun — utilise 'Bonjour,' sans nom)"}
FONDATEUR (si connu) : {founder_name or "(non connu)"}

BRAND DNA :
- mood : {brand.mood}
- palette : bg {brand.palette.bg}, primary {brand.palette.primary}, secondary {brand.palette.secondary}

URL DÉMO À INSÉRER : {demo_url}

EXPÉDITEUR (à mettre en signature ET en mentions légales) :
- Nom    : {sender.name}
- Rôle   : {sender.role}
- Société: {sender.company}
- SIREN  : {sender.siren}
- Adresse: {sender.address}

TEXTE SOURCE DU SITE EXISTANT (utilisable pour le hook spécifique) :
---
{(prospect.source_text or "(rien fourni)")[:2000]}
---

Produis l'email. Adapte le ton au mood `{brand.mood}`. Inclus impérativement les mentions légales avec ces infos expéditeur ET le placeholder {{{{unsubscribe_link}}}} à la fin. Réponds UNIQUEMENT en JSON valide.
"""


class EmailAgent:
    """Generates a ColdEmail from prospect + content + brand + sender + demo_url."""

    def __init__(self, llm: LLM | None = None, skill_path: Path | None = None):
        self.llm = llm or LLM(model=CONFIG.model_content,
                              fallback=CONFIG.model_content_fallback)
        self.skill = _load_skill(skill_path)

    def generate(
        self,
        prospect: ProspectInput,
        content: SiteContent,
        brand: BrandDNA,
        sender: SenderIdentity,
        demo_url: str,
    ) -> ColdEmail:
        last_error: str | None = None
        last_raw: str | None = None

        for attempt in range(MAX_RETRIES + 1):
            user = _build_user_prompt(
                prospect=prospect, content=content, brand=brand,
                sender=sender, demo_url=demo_url,
            )
            if last_error:
                user += (
                    f"\n\n--- TENTATIVE PRÉCÉDENTE INVALIDE ---\n"
                    f"JSON produit :\n{last_raw[:1500] if last_raw else ''}\n\n"
                    f"Erreurs :\n{last_error}\n\n"
                    f"Reproduis le JSON COMPLET corrigé."
                )

            raw = self.llm.complete_json(self.skill, user, temperature=0.7)
            last_raw = raw

            try:
                data = parse_json_robust(raw)
            except ValueError as e:
                last_error = str(e)
                console.print(f"[yellow]EmailAgent attempt {attempt+1}: invalid JSON[/]")
                continue

            try:
                return ColdEmail.model_validate(data)
            except ValidationError as e:
                last_error = e.json(indent=2)
                console.print(
                    f"[yellow]EmailAgent attempt {attempt+1}: validation failed[/]"
                )
                continue

        raise RuntimeError(
            f"ColdEmail generation failed after {MAX_RETRIES + 1} attempts.\n"
            f"Last error:\n{last_error}"
        )
