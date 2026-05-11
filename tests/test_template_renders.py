"""Smoke test: render the template with hardcoded Influence Patrimoine content.

No API key needed. Validates:
  - The Pydantic schema accepts realistic values
  - Jinja template doesn't have any syntax errors
  - Output HTML contains expected content markers
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from builder.brand_agent import DEFAULT_BRAND_DNA
from builder.image_picker import pick_hero_image
from builder.models import (
    ApproachContent,
    BrandDNA,
    Branding,
    ContactContent,
    HeroContent,
    HeroMetric,
    ManifestoContent,
    Palette,
    Service,
    ServicesContent,
    SiteContent,
    Step,
    TestimonialContent,
    Typography,
    Value,
    ValuesContent,
)
from builder.render import (
    build_google_fonts_url,
    derive_design_tokens,
    render_html,
    render_to_disk,
)


def make_influence_patrimoine_content() -> SiteContent:
    return SiteContent(
        slug="influence-patrimoine",
        sector="wealth_management",
        meta_description=(
            "Cabinet de conseil en gestion de patrimoine indépendant. Stratégies sur mesure pour "
            "créer, développer et transmettre votre patrimoine. Confiance, transparence, écoute."
        ),
        branding=Branding(
            name="Influence Patrimoine",
            subtitle="Conseil indépendant",
            letter="i",
            professional_membership="CIF · ANACOFI",
            phone="09 81 94 88 08",
            phone_tel="+33981948808",
            email="contact@influence-patrimoine.fr",
            legal_siren="",
            legal_orias="",
        ),
        hero=HeroContent(
            eyebrow="Conseiller en gestion de patrimoine",
            h1_line1="Rêvons",
            h1_line2="ensemble",
            h1_line3_before="votre ",
            h1_line3_emphasis="patrimoine.",
            h1_line3_after="",
            subtitle=(
                "Cabinet indépendant à vos côtés pour créer, développer et transmettre votre "
                "patrimoine. Une approche humaine, sur le long terme, sans conflit d'intérêts."
            ),
            cta_primary="Premier rendez-vous offert",
            cta_secondary="Découvrir notre approche",
            image_caption="Paris, VIIIᵉ",
            metrics=[
                HeroMetric(value="15+", label="années d'expérience"),
                HeroMetric(value="100%", label="indépendance & transparence"),
                HeroMetric(value="5", label="expertises patrimoniales"),
            ],
        ),
        manifesto=ManifestoContent(
            eyebrow="Notre conviction",
            quote_before="Le métier de conseiller en gestion de patrimoine est un métier ",
            quote_emphasis="humain",
            quote_after=" avant tout.",
            body=(
                "Nous mettons nos qualités d'écoute et notre savoir-faire au service de vos projets "
                "de vie. Pas de produit standardisé, pas de discours pré-écrit. Une stratégie pensée "
                "pour vous, ajustée dans le temps, expliquée simplement."
            ),
            founder_name="Jérémie",
            founder_role="Fondateur & conseiller patrimonial",
        ),
        values=ValuesContent(
            eyebrow="Nos engagements",
            h2_main="Trois principes",
            h2_emphasis="non négociables.",
            intro=(
                "Avant les performances, avant les rendements, avant les opportunités, il y a la "
                "relation que nous construisons avec vous. Trois piliers guident chacune de nos décisions."
            ),
            entries=[
                Value(title="Confiance", body=(
                    "La confiance se gagne au fil des années, pas au premier rendez-vous. C'est pourquoi "
                    "nous nous engageons à être vos compagnons de route sur la durée — disponibles, "
                    "accessibles, présents quand cela compte vraiment."
                )),
                Value(title="Transparence", body=(
                    "Nos honoraires, nos partenariats, nos rémunérations : tout est expliqué clairement, "
                    "dès le premier échange. Aucune zone d'ombre, aucun produit imposé. Vous décidez, en "
                    "pleine conscience."
                )),
                Value(title="Honnêteté", body=(
                    "Nous vous disons ce que nous pensons, même quand cela contredit vos intuitions ou "
                    "nos intérêts. Une stratégie patrimoniale solide se construit sur la lucidité, pas "
                    "sur la flatterie."
                )),
            ],
        ),
        services=ServicesContent(
            eyebrow="Nos expertises",
            h2_main="Cinq domaines,",
            h2_emphasis="une stratégie globale.",
            intro=(
                "Votre patrimoine est un tout. Nous l'abordons avec une vision d'ensemble — fiscale, "
                "immobilière, financière, successorale — pour construire une trajectoire cohérente."
            ),
            main_service=Service(
                num="01 — Approche globale",
                title="Bilan patrimonial complet",
                description=(
                    "Audit approfondi : liquidités, placements, immobilier, retraite, fiscalité, "
                    "succession. Une cartographie précise pour identifier les leviers et tracer une "
                    "stratégie sur mesure."
                ),
                is_main=True,
            ),
            other_services=[
                Service(num="02", title="Immobilier", description=(
                    "Constitution et valorisation de votre patrimoine immobilier. Loi Pinel, Malraux, "
                    "LMNP, SCPI, monuments historiques — nous orientons vers les dispositifs adaptés."
                )),
                Service(num="03", title="Épargne & placements", description=(
                    "Assurance-vie, PEA, PER, contrats de capitalisation. Allocation alignée sur votre "
                    "profil et votre horizon, pilotée dans la durée."
                )),
                Service(num="04", title="Retraite & prévoyance", description=(
                    "Anticiper votre retraite, c'est protéger votre niveau de vie. Madelin, PER, "
                    "contrats sur mesure pour structurer vos revenus futurs."
                )),
                Service(num="05", title="Défiscalisation", description=(
                    "La défiscalisation ne s'improvise pas. Nous l'inscrivons dans une stratégie de "
                    "long terme, jamais comme un produit isolé, pour réduire vos impôts sans dégrader "
                    "votre patrimoine."
                )),
            ],
        ),
        approach=ApproachContent(
            eyebrow="Notre méthode",
            h2_main="Une démarche",
            h2_emphasis="en trois temps.",
            body_p1=(
                "Le rôle d'un conseiller en gestion de patrimoine ne se résume pas à recommander des "
                "placements. C'est une démarche structurée — comprendre, analyser, construire — pour "
                "que chaque décision serve une vision d'ensemble."
            ),
            body_p2=(
                "Nous prenons le temps. Un premier rendez-vous offert, sans engagement, pour cerner "
                "votre situation. Puis un travail approfondi, des recommandations claires, et un suivi "
                "régulier dans la durée."
            ),
            steps=[
                Step(num="01", title="Écouter & comprendre", body=(
                    "Premier rendez-vous offert. Nous explorons votre situation actuelle, vos projets "
                    "de vie, votre appétence au risque, vos contraintes."
                )),
                Step(num="02", title="Auditer & recommander", body=(
                    "Bilan patrimonial complet remis sous forme écrite, accompagné de recommandations "
                    "chiffrées. Vous décidez, en toute conscience."
                )),
                Step(num="03", title="Accompagner dans la durée", body=(
                    "Mise en œuvre des solutions retenues, point annuel, ajustements à chaque évolution "
                    "de votre vie ou de la fiscalité."
                )),
            ],
        ),
        testimonial=TestimonialContent(
            eyebrow="Ils nous font confiance",
            quote=(
                "Jérémie m'a fait découvrir des choses que je ne connaissais pas. Quelques chiffres "
                "clefs, et tout de suite il m'a orienté vers les bonnes opportunités. Nous avons revu "
                "toute la structure de ma société, je lui fais entièrement confiance."
            ),
            name="Franck Verrechia",
            initials="FV",
            role="Chef d'entreprise",
        ),
        contact=ContactContent(
            eyebrow="Prenons rendez-vous",
            h2_main="Parlons de votre",
            h2_emphasis="patrimoine.",
            lead=(
                "Premier rendez-vous offert, sans engagement. En cabinet, en visioconférence ou chez "
                "vous — c'est vous qui choisissez."
            ),
            hours="Lun — Ven · 9h — 19h",
            office="Sur rendez-vous",
            form_title="Demande de rendez-vous",
            form_subtitle="Réponse personnelle sous 24 heures ouvrées.",
        ),
        footer_description=(
            "Cabinet de conseil en gestion de patrimoine indépendant. Membre de l'ANACOFI, conformité "
            "CIF & IAS."
        ),
        hero_image_url=pick_hero_image("wealth_management", "influence-patrimoine"),
        brand=DEFAULT_BRAND_DNA,
    )


def test_template_renders_without_errors():
    content = make_influence_patrimoine_content()
    html = render_html(content)
    assert len(html) > 5000
    # Spot-check expected content
    assert "Influence Patrimoine" in html
    assert "09 81 94 88 08" in html
    assert "Jérémie" in html
    assert "Confiance" in html and "Transparence" in html and "Honnêteté" in html
    assert "Bilan patrimonial complet" in html
    assert "Franck Verrechia" in html
    # Emphasis substitution worked
    assert "<em>patrimoine.</em>" in html
    assert "<em>humain</em>" in html
    # Hero image was injected
    assert "images.unsplash.com" in html


def test_render_to_disk(tmp_path):
    content = make_influence_patrimoine_content()
    out = render_to_disk(content, output_dir=tmp_path)
    assert out.exists()
    assert out.name == "index.html"
    assert out.parent.name == "influence-patrimoine"


if __name__ == "__main__":
    # Allow `python tests/test_template_renders.py` for quick manual test
    content = make_influence_patrimoine_content()
    out = render_to_disk(content)
    print(f"Rendered to: {out}")
    print(f"Hero image: {content.hero_image_url}")
    print(f"Size: {out.stat().st_size} bytes")
