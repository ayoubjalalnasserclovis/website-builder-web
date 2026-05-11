"""The content agent — turns (company name + source text) into a typed SiteContent.

Agentic loop (lightweight):
  1. Generate JSON via LLM with strict prompt + example schema
  2. Validate against Pydantic
  3. If validation fails → call LLM again with error feedback (max 2 retries)
  4. Return validated SiteContent

Pydantic does the heavy lifting: any malformed output is caught by the schema.
This keeps the template safe from garbage input.
"""

from __future__ import annotations

from rich.console import Console
from pydantic import ValidationError

from .llm import LLM, parse_json_robust
from .models import ProspectInput, SiteContent

console = Console()

MAX_RETRIES = 2

# --- Prompt ----------------------------------------------------------------

SYSTEM_PROMPT = """\
Tu es un directeur de création web pour une agence française premium. Tu produis \
le contenu de sites pour des PME françaises, dans un style éditorial sobre type \
banque privée (Edmond de Rothschild, J.P. Morgan Private Bank, Hermès).

RÈGLES NON NÉGOCIABLES :
- Tout le contenu en français, vouvoiement, ton professionnel et chaleureux
- Pas de jargon techno, pas d'emoji, pas de superlatifs creux ("le meilleur", "incroyable")
- Phrases concises et percutantes (style WIRED ou Le Monde plutôt que pub clinquante)
- Préserve scrupuleusement les noms propres, chiffres et témoignages présents dans la source
- Si une info manque (ex: nombre d'années d'expérience), génère plausiblement avec retenue
- Cohérence : ne jamais inventer de chiffres extravagants ou de prix
- Pour les italiques d'emphase : tu produis 3 segments séparés (avant, italique, après) qui se concatènent. Le segment "italique" ne doit pas être vide. Les segments "avant" et "après" peuvent être vides.

TU PRODUIS UNIQUEMENT DU JSON STRICT. Pas de markdown, pas de préambule, pas de commentaire.
"""


def _build_user_prompt(p: ProspectInput, schema_example: str) -> str:
    sector_hint = p.sector_hint or "à déduire du texte source"
    contact_block = ""
    if p.phone or p.email:
        contact_block = "\n\nCONTACT FOURNI (à utiliser tel quel) :"
        if p.phone:
            contact_block += f"\n- téléphone affichage : {p.phone}"
        if p.phone_tel:
            contact_block += f"\n- téléphone tel: link : {p.phone_tel}"
        if p.email:
            contact_block += f"\n- email : {p.email}"

    return f"""\
Génère le contenu d'un site web pour cette entreprise française.

ENTREPRISE : {p.company_name}
SLUG (URL) : {p.slug}
SECTEUR (hint) : {sector_hint}{contact_block}

TEXTE SOURCE (du site existant ou notes brutes — peut être incomplet) :
---
{p.source_text or "(aucun texte fourni — déduis tout du nom et du secteur)"}
---

Tu dois produire EXACTEMENT cette structure JSON, en remplissant chaque champ \
selon les contraintes (longueurs, valeurs autorisées). Le champ `sector` doit être \
choisi dans la liste autorisée.

{schema_example}
"""


# --- Schema example (compact, easier for LLM than raw JSON Schema) ----------

SCHEMA_EXAMPLE = """\
{
  "slug": "<slug-en-minuscules-tirets>",
  "sector": "<un de: wealth_management|law|consulting|real_estate|restaurant|healthcare|beauty|construction|ecommerce|fitness|education|creative|professional_service|default>",
  "meta_description": "<80-200 caractères, SEO, contient le nom de l'entreprise>",

  "branding": {
    "name": "<nom complet de l'entreprise>",
    "subtitle": "<sous-titre court 2-4 mots, ex: 'Conseil indépendant'>",
    "letter": "<1 lettre minuscule pour le monogramme, idéalement la 1ère du nom>",
    "professional_membership": "<si pertinent, ex: 'CIF · ANACOFI'. Sinon ''>",
    "phone": "<format affichage, ex: '09 81 94 88 08'>",
    "phone_tel": "<format tel:, ex: '+33981948808'>",
    "email": "<email de contact>",
    "legal_siren": "",
    "legal_orias": ""
  },

  "hero": {
    "eyebrow": "<rôle/positionnement court, ex: 'Conseiller en gestion de patrimoine'>",
    "h1_line1": "<première ligne du titre, ex: 'Rêvons'>",
    "h1_line2": "<deuxième ligne, ex: 'ensemble'>",
    "h1_line3_before": "<début de la 3e ligne avant l'italique, ex: 'votre '. Peut être vide.>",
    "h1_line3_emphasis": "<partie en italique doré, ex: 'patrimoine.'>",
    "h1_line3_after": "<suite après l'italique, ex: ''. Peut être vide.>",
    "subtitle": "<1-2 phrases qui clarifient l'offre, 80-240 caractères>",
    "cta_primary": "<CTA principal, ex: 'Premier rendez-vous offert'>",
    "cta_secondary": "<CTA secondaire, ex: 'Découvrir notre approche'>",
    "image_caption": "<petit caption sous l'image, ex: 'Paris, VIIIᵉ' ou ''>",
    "metrics": [
      {"value": "<ex: '15+'>", "label": "<ex: \\"années d'expérience\\">"},
      {"value": "<ex: '100%'>", "label": "<ex: 'indépendance & transparence'>"},
      {"value": "<ex: '5'>", "label": "<ex: 'expertises proposées'>"}
    ]
  },

  "manifesto": {
    "eyebrow": "<ex: 'Notre conviction'>",
    "quote_before": "<début de la citation avant l'italique. Ex: 'Le métier de conseiller est un métier '>",
    "quote_emphasis": "<partie en italique. Ex: 'humain'>",
    "quote_after": "<fin de la citation après l'italique. Ex: ' avant tout.'>",
    "body": "<paragraphe explicatif, 120-520 caractères>",
    "founder_name": "<prénom ou prénom+nom du fondateur si mentionné, sinon le nom du dirigeant ou un placeholder cohérent>",
    "founder_role": "<ex: 'Fondateur & dirigeant'>"
  },

  "values": {
    "eyebrow": "<ex: 'Nos engagements'>",
    "h2_main": "<première partie du titre>",
    "h2_emphasis": "<suite italique dorée>",
    "intro": "<80-320 caractères>",
    "entries": [
      {"title": "<un mot>", "body": "<2-3 phrases, 80-320 caractères>"},
      {"title": "<un mot>", "body": "<2-3 phrases, 80-320 caractères>"},
      {"title": "<un mot>", "body": "<2-3 phrases, 80-320 caractères>"}
    ]
  },

  "services": {
    "eyebrow": "<ex: 'Nos expertises'>",
    "h2_main": "<première partie>",
    "h2_emphasis": "<suite italique>",
    "intro": "<80-320 caractères>",
    "main_service": {
      "num": "01 — <petit qualificatif>",
      "title": "<service phare>",
      "description": "<2-3 phrases percutantes, 80-320 caractères>",
      "is_main": true
    },
    "other_services": [
      {"num": "02", "title": "...", "description": "...", "is_main": false},
      {"num": "03", "title": "...", "description": "...", "is_main": false},
      {"num": "04", "title": "...", "description": "...", "is_main": false},
      {"num": "05", "title": "...", "description": "...", "is_main": false}
    ]
  },

  "approach": {
    "eyebrow": "<ex: 'Notre méthode'>",
    "h2_main": "<première partie>",
    "h2_emphasis": "<suite italique>",
    "body_p1": "<paragraphe 1>",
    "body_p2": "<paragraphe 2>",
    "steps": [
      {"num": "01", "title": "...", "body": "..."},
      {"num": "02", "title": "...", "body": "..."},
      {"num": "03", "title": "...", "body": "..."}
    ]
  },

  "testimonial": {
    "eyebrow": "<ex: 'Ils nous font confiance'>",
    "quote": "<si témoignage présent dans la source, l'utiliser quasi tel quel; sinon générer un témoignage plausible et sobre>",
    "name": "<nom complet>",
    "initials": "<2-3 lettres>",
    "role": "<ex: 'Chef d\\'entreprise', 'Cliente depuis 2019'>"
  },

  "contact": {
    "eyebrow": "<ex: 'Prenons rendez-vous'>",
    "h2_main": "<première partie>",
    "h2_emphasis": "<suite italique>",
    "lead": "<80-320 caractères>",
    "hours": "<ex: 'Lun — Ven · 9h — 19h'>",
    "office": "<ex: 'Sur rendez-vous'>",
    "form_title": "<ex: 'Demande de rendez-vous'>",
    "form_subtitle": "<une phrase courte>"
  },

  "footer_description": "<80-240 caractères, présentation de l'entreprise pour le footer>"
}
"""


# --- Public API -------------------------------------------------------------

class ContentAgent:
    """Generates SiteContent from a ProspectInput, with validation retries."""

    def __init__(self, llm: LLM | None = None):
        self.llm = llm or LLM()

    def generate(self, prospect: ProspectInput) -> SiteContent:
        last_error: str | None = None
        last_raw: str | None = None

        for attempt in range(MAX_RETRIES + 1):
            user = _build_user_prompt(prospect, SCHEMA_EXAMPLE)
            if last_error:
                user += (
                    f"\n\n--- TENTATIVE PRÉCÉDENTE INVALIDE ---\n"
                    f"Tu as produit ce JSON :\n{last_raw[:1500] if last_raw else ''}\n\n"
                    f"Erreurs de validation :\n{last_error}\n\n"
                    f"Corrige UNIQUEMENT les champs problématiques et reproduit "
                    f"le JSON COMPLET corrigé."
                )

            raw = self.llm.complete_json(SYSTEM_PROMPT, user)
            last_raw = raw

            try:
                data = parse_json_robust(raw)
            except ValueError as e:
                last_error = str(e)
                console.print(f"[yellow]Attempt {attempt+1}: invalid JSON, retrying...[/]")
                continue

            try:
                # Slug & sector_hint may need to come from input
                if "slug" not in data or not data["slug"]:
                    data["slug"] = prospect.slug
                content = SiteContent.model_validate(data)
                return content
            except ValidationError as e:
                last_error = e.json(indent=2)
                console.print(f"[yellow]Attempt {attempt+1}: validation failed, retrying...[/]")
                continue

        raise RuntimeError(
            f"Content generation failed after {MAX_RETRIES + 1} attempts.\n"
            f"Last error:\n{last_error}"
        )
