"""Render a sample cold email (no API call) so we can preview the HTML layout.

Uses a mocked LLM that returns a realistic French copy for Influence Patrimoine.
The output is what would be pushed to Instantly as `personalization.body_html`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rich.console import Console

from builder.email_agent import EmailAgent
from builder.models import (
    ApproachContent, BrandDNA, Branding, ContactContent, HeroContent,
    HeroMetric, ManifestoContent, Palette, ProspectInput, SenderIdentity,
    Service, ServicesContent, SiteContent, Step, TestimonialContent,
    Typography, Value, ValuesContent,
)

console = Console()


# A realistic, RGPD-compliant email — what the LLM should produce
SAMPLE_EMAIL_JSON = json.dumps({
    "subject": "idée pour le site d'Influence Patrimoine",
    "preheader": "Une démo de site moderne, déjà construite. À voir.",
    "body_text": (
        "Bonjour Jérémie,\n\n"
        "J'ai jeté un œil au site actuel d'Influence Patrimoine. "
        "L'approche humaine du métier transparaît dans les témoignages — "
        "Franck Verrechia est convaincant — mais le cadre visuel le dessert un peu.\n\n"
        "J'ai construit une démo moderne pour Influence Patrimoine, "
        "dans l'esprit banque privée. Sans engagement, à voir ici :\n"
        "https://demos.tonagence.fr/influence-patrimoine/\n\n"
        "Si la direction vous parle, on peut en discuter 15 minutes — "
        "sinon, ignorez ce mail.\n\n"
        "Bien à vous,\n"
        "Alex Dubois\n"
        "Cofondateur — Mon Agence Web SAS\n"
        "+33 6 12 34 56 78\n\n"
        "---\n"
        "Alex Dubois — Mon Agence Web SAS — SIREN 903456789\n"
        "12 rue de la République, 75011 Paris\n\n"
        "Cet email vous est adressé dans le cadre d'une démarche de "
        "prospection commerciale B2B (RGPD art. 6.1.f, intérêt légitime). "
        "Vous pouvez vous désinscrire à tout moment via le lien ci-dessous."
    ),
    "body_html": (
        "<p>Bonjour Jérémie,</p>"
        "<p>J'ai jeté un œil au site actuel d'Influence Patrimoine. "
        "L'approche humaine du métier transparaît dans les témoignages — "
        "Franck Verrechia est convaincant — mais le cadre visuel le dessert un peu.</p>"
        "<p>J'ai construit une démo moderne pour Influence Patrimoine, "
        "dans l'esprit banque privée. Sans engagement, à voir ici : "
        "<a href=\"https://demos.tonagence.fr/influence-patrimoine/\" "
        "style=\"color: #14213D; text-decoration: underline;\">"
        "demos.tonagence.fr/influence-patrimoine</a>.</p>"
        "<p>Si la direction vous parle, on peut en discuter 15 minutes — "
        "sinon, ignorez ce mail.</p>"
        "<p>Bien à vous,<br>"
        "<strong>Alex Dubois</strong><br>"
        "Cofondateur · Mon Agence Web SAS<br>"
        "+33 6 12 34 56 78</p>"
        "<small style=\"color: #888; font-size: 11px; line-height: 1.5; "
        "display: block; margin-top: 24px; border-top: 1px solid #ddd; padding-top: 16px;\">"
        "Alex Dubois — Mon Agence Web SAS — SIREN 903456789<br>"
        "12 rue de la République, 75011 Paris<br><br>"
        "Cet email vous est adressé dans le cadre d'une démarche de prospection "
        "commerciale B2B, sur la base de l'intérêt légitime "
        "(<a href=\"https://www.cnil.fr/\" style=\"color:#888;\">RGPD art. 6.1.f</a>), "
        "parce que nous avons identifié Influence Patrimoine comme potentiellement "
        "intéressé par nos services.<br>"
        "Vous pouvez vous désinscrire à tout moment via le lien ci-dessous."
        "<br><br>{{unsubscribe_link}}"
        "</small>"
    ),
    "rationale": (
        "Hook spécifique sur le témoignage de Franck Verrechia (mentionné dans la "
        "source) pour montrer une vraie lecture. Ton refined adapté à un cabinet "
        "patrimonial, vouvoiement, phrases construites mais courtes."
    ),
})


def main():
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = SAMPLE_EMAIL_JSON

    agent = EmailAgent(llm=fake_llm)
    sender = SenderIdentity(
        name="Alex Dubois", role="Cofondateur",
        company="Mon Agence Web SAS",
        siren="903456789",
        address="12 rue de la République, 75011 Paris",
        phone="+33612345678",
        reply_to_email="alex@monagenceweb.fr",
    )

    # Minimal but valid SiteContent for Influence Patrimoine (just for context)
    brand = BrandDNA(
        palette=Palette(bg="#F4EFE5", surface="#EAE3D2", text="#1B1B1F",
                        primary="#14213D", secondary="#B89968"),
        typography=Typography(display_font="Fraunces", body_font="Inter"),
        mood="refined", layout_variant="editorial_classic",
        rationale="Navy / cream / gold pour la banque privée.",
    )

    # Build a content stub (real one comes from DB in production)
    content = SiteContent(
        slug="influence-patrimoine", sector="wealth_management",
        meta_description="x" * 100,
        branding=Branding(
            name="Influence Patrimoine", subtitle="Conseil indépendant", letter="i",
            phone="0981948808", phone_tel="+33981948808",
            email="contact@influence-patrimoine.fr",
        ),
        hero=HeroContent(
            eyebrow="x", h1_line1="A", h1_line2="B", h1_line3_emphasis="CC",
            subtitle="x" * 100, cta_primary="Y", cta_secondary="Z",
            metrics=[HeroMetric(value=str(i), label=f"l{i}") for i in range(1, 4)],
        ),
        manifesto=ManifestoContent(
            eyebrow="x", quote_before="ab", quote_emphasis="mn", quote_after="cd",
            body="x" * 130, founder_name="Jérémie", founder_role="Fondateur",
        ),
        values=ValuesContent(
            eyebrow="x", h2_main="A", h2_emphasis="B", intro="x" * 100,
            entries=[Value(title=f"V{i}", body="x" * 100) for i in range(3)],
        ),
        services=ServicesContent(
            eyebrow="x", h2_main="A", h2_emphasis="B", intro="x" * 100,
            main_service=Service(num="01", title="A", description="x" * 100, is_main=True),
            other_services=[Service(num=str(i), title=f"S{i}", description="x"*100)
                            for i in range(2, 6)],
        ),
        approach=ApproachContent(
            eyebrow="x", h2_main="A", h2_emphasis="B",
            body_p1="x"*100, body_p2="x"*100,
            steps=[Step(num=str(i), title=f"T{i}", body="x"*100) for i in range(1, 4)],
        ),
        testimonial=TestimonialContent(
            eyebrow="x", quote="x"*100, name="A", initials="AB", role="x",
        ),
        contact=ContactContent(
            eyebrow="x", h2_main="A", h2_emphasis="B", lead="x"*100,
            hours="x", office="x", form_title="x", form_subtitle="x",
        ),
        footer_description="x"*100,
        brand=brand,
    )

    prospect = ProspectInput(
        slug="influence-patrimoine", company_name="Influence Patrimoine",
        email="contact@influence-patrimoine.fr", sector_hint="wealth_management",
        source_text=(
            "Cabinet de conseil en gestion de patrimoine indépendant. Témoignage de "
            "Franck Verrechia : 'Jérémie m'a aidé à découvrir des opportunités.'"
        ),
    )

    email = agent.generate(prospect=prospect, content=content, brand=brand,
                           sender=sender,
                           demo_url="https://demos.tonagence.fr/influence-patrimoine/")

    console.print("[bold]Generated cold email:[/]\n")
    console.print(f"[cyan]Subject:[/] {email.subject}")
    console.print(f"[cyan]Preheader:[/] {email.preheader}\n")
    console.print(f"[cyan]Body (text):[/]\n{email.body_text}\n")
    console.print(f"[cyan]Rationale:[/] {email.rationale}\n")

    # Render the HTML body inside a basic preview document
    preview = (
        "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
        "<title>Cold email preview</title>"
        "<style>"
        "body { font-family: 'Inter', -apple-system, sans-serif; "
        "background: #F2EEE6; color: #15151A; max-width: 640px; margin: 40px auto; "
        "padding: 32px; line-height: 1.55; }"
        ".meta { background: #ECE6DA; padding: 16px 20px; border-radius: 4px; "
        "font-size: 13px; color: #6B6F7A; margin-bottom: 28px; }"
        ".meta strong { color: #14213D; }"
        ".email-body { background: white; padding: 32px 36px; border-radius: 4px; "
        "border: 1px solid rgba(20,33,61,.1); font-size: 15px; }"
        ".email-body p { margin: 0 0 14px; }"
        "h2 { font-family: 'Fraunces', serif; font-weight: 400; font-size: 28px; "
        "margin: 0 0 8px; color: #14213D; }"
        ".tag { display: inline-block; background: #14213D; color: #F2EEE6; "
        "font-size: 11px; padding: 4px 10px; border-radius: 2px; "
        "letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 16px; }"
        "</style></head><body>"
        "<span class='tag'>Cold email — preview</span>"
        f"<h2>{email.subject}</h2>"
        "<div class='meta'>"
        "<strong>De :</strong> Alex Dubois &lt;alex@monagenceweb.fr&gt;<br>"
        "<strong>À :</strong> contact@influence-patrimoine.fr<br>"
        f"<strong>Aperçu :</strong> {email.preheader}"
        "</div>"
        f"<div class='email-body'>{email.body_html}</div>"
        "</body></html>"
    )

    out = Path("dist/_demo_email.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(preview, encoding="utf-8")
    console.print(f"\n[green]Preview HTML written to:[/] {out}")


if __name__ == "__main__":
    main()
