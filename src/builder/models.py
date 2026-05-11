"""Pydantic schemas — the strict contract between LLM and template.

Any LLM output that doesn't match these models is rejected and retried.
This is what makes the builder solid at scale: the template can never
break because of malformed content.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# --- Enumerated sectors (the LLM must pick one) -----------------------------

Sector = Literal[
    "wealth_management",   # CGP, banque privée, conseil en patrimoine
    "law",                 # avocat, notaire, juriste
    "consulting",          # conseil, audit, stratégie
    "real_estate",         # agence immobilière, syndic, promoteur
    "restaurant",          # restaurant, bistrot, traiteur
    "healthcare",          # médecin, kiné, dentiste, ostéopathe
    "beauty",              # coiffeur, esthétique, spa
    "construction",        # BTP, artisan, entrepreneur
    "ecommerce",           # boutique en ligne, retail
    "fitness",             # salle de sport, coach, yoga
    "education",           # école, formation, coaching
    "creative",            # agence, studio, photographe
    "professional_service", # comptable, notaire, expert-comptable
    "default",             # fallback générique premium
]


# --- Sub-models -------------------------------------------------------------

class HeroMetric(BaseModel):
    value: str = Field(..., max_length=10, description="Ex: '15+', '100%', '5'")
    label: str = Field(..., max_length=60, description="Ex: 'années d\\'expérience'")


class Value(BaseModel):
    title: str = Field(..., max_length=24, description="Un mot. Ex: 'Confiance'")
    body: str = Field(..., min_length=80, max_length=320,
                      description="2–3 phrases. Vouvoiement.")


class Service(BaseModel):
    num: str = Field(..., max_length=40,
                     description="'01', '02', etc. Pour le service phare, peut être 'XX — qualificatif'")
    title: str = Field(..., max_length=40, description="Ex: 'Bilan patrimonial'")
    description: str = Field(..., min_length=80, max_length=320,
                             description="2–3 phrases percutantes.")
    is_main: bool = Field(False, description="True pour le service phare (carte large)")


class Step(BaseModel):
    num: str = Field(..., max_length=4, description="Ex: '01'")
    title: str = Field(..., max_length=40)
    body: str = Field(..., min_length=80, max_length=260)


# --- Section-level models ---------------------------------------------------

class Branding(BaseModel):
    name: str = Field(..., max_length=60, description="Nom complet de l'entreprise")
    subtitle: str = Field(..., max_length=40,
                          description="Sous-titre court. Ex: 'Conseil indépendant'")
    letter: str = Field(..., max_length=2,
                        description="1 lettre minuscule pour le monogramme")
    professional_membership: str = Field("", max_length=60,
                                         description="Mentions ordinales si applicable. Ex: 'CIF · ANACOFI'. Vide si pas pertinent.")
    phone: str = Field(..., description="Format affichage. Ex: '09 81 94 88 08'")
    phone_tel: str = Field(..., description="Format tel: link. Ex: '+33981948808'")
    email: str = Field(..., description="Email de contact")
    legal_siren: str = Field("", description="SIREN si dispo")
    legal_orias: str = Field("", description="ORIAS si dispo")

    @field_validator("letter")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()[:1]


class HeroContent(BaseModel):
    eyebrow: str = Field(..., max_length=60,
                         description="Petite ligne au-dessus du H1. Ex: 'Conseiller en gestion de patrimoine'")
    # H1 = trois lignes. La 3ème est en 3 segments pour gérer l'italique sans matching :
    #   {h1_line3_before}<em>{h1_line3_emphasis}</em>{h1_line3_after}
    h1_line1: str = Field(..., max_length=24, description="Ex: 'Rêvons'")
    h1_line2: str = Field(..., max_length=24, description="Ex: 'ensemble'")
    h1_line3_before: str = Field("", max_length=24,
                                 description="Texte avant l'italique. Ex: 'votre '. Peut être vide.")
    h1_line3_emphasis: str = Field(..., min_length=1, max_length=24,
                                   description="Texte en italique doré. Ex: 'patrimoine.'")
    h1_line3_after: str = Field("", max_length=24,
                                description="Texte après l'italique. Souvent vide.")
    subtitle: str = Field(..., min_length=80, max_length=240,
                          description="1–2 phrases qui clarifient l'offre.")
    cta_primary: str = Field(..., max_length=40, description="Ex: 'Premier rendez-vous offert'")
    cta_secondary: str = Field(..., max_length=40, description="Ex: 'Découvrir notre approche'")
    image_caption: str = Field("", max_length=30,
                               description="Petit caption en bas de l'image hero. Ex: 'Paris, VIIIᵉ'")
    metrics: List[HeroMetric] = Field(..., min_length=3, max_length=3,
                                      description="Exactement 3 métriques.")


class ManifestoContent(BaseModel):
    eyebrow: str = Field(..., max_length=40)
    # Quote = trois segments pour rendre l'italique sans matching texte :
    #   {quote_before}<em>{quote_emphasis}</em>{quote_after}
    quote_before: str = Field("", max_length=200,
                              description="Texte avant l'italique.")
    quote_emphasis: str = Field(..., min_length=2, max_length=80,
                                description="Texte en italique doré.")
    quote_after: str = Field("", max_length=200,
                             description="Texte après l'italique.")
    body: str = Field(..., min_length=120, max_length=520,
                      description="Paragraphe explicatif sous la quote.")
    founder_name: str = Field(..., max_length=60)
    founder_role: str = Field(..., max_length=60)


class ValuesContent(BaseModel):
    eyebrow: str = Field(..., max_length=40)
    h2_main: str = Field(..., max_length=60,
                         description="Première partie du titre. Ex: 'Trois principes'")
    h2_emphasis: str = Field(..., max_length=40,
                             description="Suite italique dorée. Ex: 'non négociables.'")
    intro: str = Field(..., min_length=80, max_length=320)
    entries: List[Value] = Field(..., min_length=3, max_length=3,
                                 description="Exactement 3 valeurs.")


class ServicesContent(BaseModel):
    eyebrow: str = Field(..., max_length=40)
    h2_main: str = Field(..., max_length=60)
    h2_emphasis: str = Field(..., max_length=40)
    intro: str = Field(..., min_length=80, max_length=320)
    main_service: Service = Field(..., description="Service phare (carte large)")
    other_services: List[Service] = Field(..., min_length=4, max_length=4,
                                          description="Exactement 4 services secondaires.")


class ApproachContent(BaseModel):
    eyebrow: str = Field(..., max_length=40)
    h2_main: str = Field(..., max_length=60)
    h2_emphasis: str = Field(..., max_length=40)
    body_p1: str = Field(..., min_length=80, max_length=320)
    body_p2: str = Field(..., min_length=80, max_length=320)
    steps: List[Step] = Field(..., min_length=3, max_length=3)


class TestimonialContent(BaseModel):
    eyebrow: str = Field(..., max_length=40)
    quote: str = Field(..., min_length=80, max_length=400)
    name: str = Field(..., max_length=60)
    initials: str = Field(..., max_length=4)
    role: str = Field(..., max_length=60)


class ContactContent(BaseModel):
    eyebrow: str = Field(..., max_length=40)
    h2_main: str = Field(..., max_length=60)
    h2_emphasis: str = Field(..., max_length=40)
    lead: str = Field(..., min_length=60, max_length=320)
    hours: str = Field(..., max_length=40, description="Ex: 'Lun — Ven · 9h — 19h'")
    office: str = Field(..., max_length=40, description="Ex: 'Sur rendez-vous'")
    form_title: str = Field(..., max_length=40)
    form_subtitle: str = Field(..., max_length=120)


# --- Brand DNA (Phase 5 — design director) ----------------------------------

Mood = Literal["refined", "warm", "bold", "grounded", "intellectual"]
LayoutVariant = Literal["editorial_classic", "editorial_asymmetric", "gallery_minimal"]

# Whitelist of fonts the design director may pick. If the LLM goes off-list,
# Pydantic rejects → retry. Keeps the Google Fonts URL builder safe.
ApprovedFont = Literal[
    "Fraunces", "Cormorant Garamond", "Playfair Display", "DM Serif Display",
    "Domine", "Bricolage Grotesque", "Outfit", "Space Grotesk", "Tenor Sans",
    "Recoleta", "EB Garamond", "Anton",
    "Inter", "Source Sans 3", "DM Sans", "Public Sans", "Manrope",
    "Albert Sans",
]

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class Palette(BaseModel):
    """5 hex colors that drive the entire site's visual identity."""
    bg: str = Field(..., description="Page background. Never pure white.")
    surface: str = Field(..., description="Subtle contrast vs bg, for cards/sections.")
    text: str = Field(..., description="Body copy color. Strong contrast vs bg.")
    primary: str = Field(..., description="Brand accent for CTAs, italic emphasis.")
    secondary: str = Field(..., description="Supporting accent (gold, bronze, dust...).")

    @field_validator("bg", "surface", "text", "primary", "secondary")
    @classmethod
    def _hex_format(cls, v: str) -> str:
        if not _HEX_RE.match(v):
            raise ValueError(f"Color must be #RRGGBB, got {v!r}")
        return v.upper()


class Typography(BaseModel):
    """One display font + one body font, both from the approved Google Fonts list."""
    display_font: ApprovedFont
    body_font: ApprovedFont


class BrandDNA(BaseModel):
    """The visual identity output by the design director agent.

    Each website gets a unique BrandDNA. The renderer maps it to CSS variables
    and a Google Fonts URL — the same template skeleton can produce visually
    distinct sites without any HTML duplication.
    """
    palette: Palette
    typography: Typography
    mood: Mood
    layout_variant: LayoutVariant
    rationale: str = Field(..., min_length=20, max_length=600,
                           description="2–3 sentences (FR) explaining the design choices.")


# --- Top-level model --------------------------------------------------------

class SiteContent(BaseModel):
    """The complete content schema. Maps 1:1 to the Jinja template variables."""

    slug: str = Field(..., min_length=2, max_length=80,
                      description="URL slug. Lowercase, no spaces.")
    sector: Sector = Field(..., description="Used to pick the hero image.")
    meta_description: str = Field(..., min_length=80, max_length=200,
                                  description="SEO meta description.")

    branding: Branding
    hero: HeroContent
    manifesto: ManifestoContent
    values: ValuesContent
    services: ServicesContent
    approach: ApproachContent
    testimonial: TestimonialContent
    contact: ContactContent

    footer_description: str = Field(..., min_length=80, max_length=240)

    # Filled by builder, not by LLM:
    hero_image_url: str = ""
    brand: Optional[BrandDNA] = Field(default=None,
        description="Visual identity for this site. Defaults to a refined navy/cream/gold "
                    "if not set (legacy support).")
    current_year: int = Field(default_factory=lambda: datetime.now().year)


# --- Input model (what the user provides) -----------------------------------

class ProspectInput(BaseModel):
    """One row of the input CSV."""

    slug: str = Field(..., description="Used as URL path. Auto-generated if empty.")
    company_name: str
    source_text: str = Field("",
                             description="Texte brut du site existant ou notes. Peut être vide.")
    sector_hint: Optional[Sector] = None
    phone: Optional[str] = None
    phone_tel: Optional[str] = None
    email: Optional[str] = None
    hero_image_url: Optional[str] = None  # Override the auto-picked image


# --- Cold email models (Phase 6) -------------------------------------------

class SenderIdentity(BaseModel):
    """Who's sending the cold email. Required for RGPD compliance."""
    name: str = Field(..., max_length=80, description="Ex: 'Alex Dubois'")
    role: str = Field(..., max_length=80, description="Ex: 'Cofondateur'")
    company: str = Field(..., max_length=80, description="Raison sociale")
    siren: str = Field(..., min_length=9, max_length=14,
                       description="SIREN (9 chiffres) ou SIRET (14 chiffres)")
    address: str = Field(..., max_length=200,
                         description="Adresse postale complète, ex: '12 rue X, 75001 Paris'")
    phone: Optional[str] = Field(None, max_length=20)
    reply_to_email: str = Field(..., description="Email auquel les réponses arrivent")


class ColdEmail(BaseModel):
    """A single personalized cold email ready to push to Instantly."""
    subject: str = Field(..., min_length=8, max_length=52)
    preheader: str = Field(..., min_length=20, max_length=90,
                           description="Aperçu Gmail/Outlook")
    body_text: str = Field(..., min_length=80, max_length=2000,
                           description="Plain text version (< 200 mots)")
    body_html: str = Field(..., min_length=120, max_length=4000,
                           description="HTML simple — doit contenir {{unsubscribe_link}}")
    rationale: str = Field(..., min_length=20, max_length=400)

    @field_validator("body_html")
    @classmethod
    def _must_have_unsubscribe(cls, v: str) -> str:
        if "{{unsubscribe_link}}" not in v and "{{unsubscribe}}" not in v:
            raise ValueError(
                "body_html must include the {{unsubscribe_link}} placeholder "
                "(RGPD compliance)"
            )
        return v


# --- QA models (Phase 4) ----------------------------------------------------

QASeverity = Literal["critical", "minor", "polish"]
QAArea = Literal["typography", "layout", "image", "content", "language", "consistency"]


class QAFinding(BaseModel):
    severity: QASeverity = Field(..., description="critical = bloquant ; minor = à corriger ; polish = nice-to-have")
    area: QAArea
    description: str = Field(..., min_length=10, max_length=240)


class QAReport(BaseModel):
    """Vision LLM output for one screenshot."""
    score: int = Field(..., ge=0, le=10, description="Score global 0–10")
    verdict: Literal["pass", "reject"] = Field(...,
        description="pass si score ≥ seuil ET aucun finding 'critical', sinon reject")
    summary: str = Field(..., min_length=20, max_length=400,
                         description="1-2 phrases de synthèse en français")
    findings: List[QAFinding] = Field(default_factory=list, max_length=15)
