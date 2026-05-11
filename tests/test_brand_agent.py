"""Tests for the brand DNA agent + design tokens.

Covers:
  - BrandDNA Pydantic validation (hex format, font whitelist, mood, layout enums)
  - design tokens derivation (light vs dark themes, footer color logic)
  - Google Fonts URL builder
  - The agent's retry-on-validation-error loop (mocked LLM)
  - That the same template skeleton produces visibly different HTML for
    different BrandDNAs (the whole point of Phase 5)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from builder.brand_agent import DEFAULT_BRAND_DNA, BrandAgent, _load_skill
from builder.models import BrandDNA, Palette, Typography
from builder.render import build_google_fonts_url, derive_design_tokens, render_html


# --- Pydantic validation ---------------------------------------------------

def test_palette_rejects_invalid_hex():
    with pytest.raises(ValidationError):
        Palette(bg="not-a-color", surface="#FFFFFF", text="#000000",
                primary="#000000", secondary="#000000")


def test_palette_normalizes_hex_to_uppercase():
    p = Palette(bg="#abcdef", surface="#FFF000", text="#000000",
                primary="#123456", secondary="#789ABC")
    assert p.bg == "#ABCDEF"


def test_typography_rejects_unknown_font():
    with pytest.raises(ValidationError):
        Typography(display_font="ComicSansForever", body_font="Inter")


def test_branddna_rejects_invalid_mood():
    with pytest.raises(ValidationError):
        BrandDNA(
            palette=Palette(bg="#F0F0F0", surface="#E0E0E0", text="#000000",
                            primary="#000000", secondary="#000000"),
            typography=Typography(display_font="Inter", body_font="Inter"),
            mood="vibey",  # invalid
            layout_variant="editorial_classic",
            rationale="x" * 30,
        )


# --- Design token derivation -----------------------------------------------

def test_derive_tokens_light_theme():
    brand = DEFAULT_BRAND_DNA  # bg = #F4EFE5 (light)
    tokens = derive_design_tokens(brand)
    assert tokens["color_bg"] == brand.palette.bg
    assert tokens["color_primary"] == brand.palette.primary
    assert tokens["is_dark_theme"] is False
    # Footer should be darker than the bg on a light theme
    assert tokens["color_footer_bg"] != tokens["color_bg"]


def test_derive_tokens_dark_theme():
    dark_brand = BrandDNA(
        palette=Palette(bg="#0F1115", surface="#1A1D24", text="#F0EFEA",
                        primary="#D9614C", secondary="#A89B85"),
        typography=Typography(display_font="Inter", body_font="Inter"),
        mood="bold",
        layout_variant="editorial_classic",
        rationale="x" * 30,
    )
    tokens = derive_design_tokens(dark_brand)
    assert tokens["is_dark_theme"] is True


# --- Google Fonts URL ------------------------------------------------------

def test_google_fonts_url_builds_two_families():
    url = build_google_fonts_url("Fraunces", "Inter")
    assert url.startswith("https://fonts.googleapis.com/css2?")
    assert "family=Fraunces" in url
    assert "family=Inter" in url
    assert url.endswith("&display=swap")


def test_google_fonts_url_dedupes_same_font():
    """If display == body (sans/sans pair), don't request the same family twice."""
    url = build_google_fonts_url("Manrope", "Manrope")
    assert url.count("family=Manrope") == 1


def test_google_fonts_url_encodes_spaces():
    url = build_google_fonts_url("Cormorant Garamond", "Inter")
    # 'Cormorant Garamond' becomes URL-encoded
    assert "Cormorant%20Garamond" in url or "Cormorant+Garamond" in url


# --- Skill loading ---------------------------------------------------------

def test_load_skill_returns_markdown():
    skill = _load_skill()
    assert "Directeur Artistique" in skill
    assert "palette" in skill.lower()
    assert "google fonts" in skill.lower() or "fraunces" in skill.lower()


# --- Brand agent retry loop ------------------------------------------------

def test_brand_agent_retries_on_invalid_json():
    """First attempt returns garbage, second returns valid → agent recovers."""
    fake_llm = MagicMock()
    fake_llm.complete_json.side_effect = [
        "this is not json",
        json.dumps({
            "palette": {
                "bg": "#F4EFE5", "surface": "#E8DDC9", "text": "#1B1B1F",
                "primary": "#1A2942", "secondary": "#B27240",
            },
            "typography": {"display_font": "Fraunces", "body_font": "Inter"},
            "mood": "refined",
            "layout_variant": "editorial_classic",
            "rationale": "Palette navy / parchment / copper inspirée de la banque privée.",
        }),
    ]

    from builder.models import ProspectInput
    agent = BrandAgent(llm=fake_llm)
    result = agent.generate(ProspectInput(
        slug="test", company_name="Test SARL",
        source_text="Cabinet de conseil patrimonial",
    ))

    assert result.palette.primary == "#1A2942"
    assert result.typography.display_font == "Fraunces"
    assert fake_llm.complete_json.call_count == 2


def test_brand_agent_raises_after_max_retries():
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = "still garbage"

    from builder.models import ProspectInput
    agent = BrandAgent(llm=fake_llm)
    with pytest.raises(RuntimeError, match="failed after"):
        agent.generate(ProspectInput(
            slug="test", company_name="Test SARL",
        ))


# --- Visible variety (the actual point of Phase 5) -------------------------

def _minimal_content(slug, brand):
    """Build a minimal valid SiteContent with the given brand DNA."""
    from builder.models import (ApproachContent, Branding, ContactContent,
                                  HeroContent, HeroMetric, ManifestoContent,
                                  Service, ServicesContent, SiteContent, Step,
                                  TestimonialContent, Value, ValuesContent)
    return SiteContent(
        slug=slug, sector="default",
        meta_description="x" * 100,
        branding=Branding(name="Test", subtitle="Sub", letter="t",
                          phone="01 02 03 04 05", phone_tel="+33102030405",
                          email="x@test.fr"),
        hero=HeroContent(
            eyebrow="x", h1_line1="A", h1_line2="B", h1_line3_emphasis="C",
            subtitle="x" * 100, cta_primary="Y", cta_secondary="Z",
            metrics=[HeroMetric(value="1", label="x"),
                     HeroMetric(value="2", label="y"),
                     HeroMetric(value="3", label="z")],
        ),
        manifesto=ManifestoContent(
            eyebrow="x", quote_before="ab", quote_emphasis="mn", quote_after="cd",
            body="x" * 130, founder_name="A", founder_role="B",
        ),
        values=ValuesContent(
            eyebrow="x", h2_main="A", h2_emphasis="B", intro="x" * 100,
            entries=[Value(title="A", body="x" * 100),
                     Value(title="B", body="x" * 100),
                     Value(title="C", body="x" * 100)],
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
            steps=[Step(num="01", title="A", body="x"*100),
                   Step(num="02", title="B", body="x"*100),
                   Step(num="03", title="C", body="x"*100)],
        ),
        testimonial=TestimonialContent(
            eyebrow="x", quote="x"*100, name="A", initials="AB", role="x",
        ),
        contact=ContactContent(
            eyebrow="x", h2_main="A", h2_emphasis="B", lead="x"*100,
            hours="x", office="x", form_title="x", form_subtitle="x",
        ),
        footer_description="x" * 100,
        brand=brand,
    )


def test_different_brand_dnas_produce_visibly_different_html():
    """Same content, two different BrandDNAs → HTML must differ in colors AND fonts."""
    refined = BrandDNA(
        palette=Palette(bg="#F4EFE5", surface="#EAE3D2", text="#1B1B1F",
                        primary="#14213D", secondary="#B89968"),
        typography=Typography(display_font="Fraunces", body_font="Inter"),
        mood="refined", layout_variant="editorial_classic",
        rationale="x" * 30,
    )
    grounded = BrandDNA(
        palette=Palette(bg="#E8DDC9", surface="#D4C4A8", text="#1A1612",
                        primary="#A04C2D", secondary="#3F3D3A"),
        typography=Typography(display_font="Bricolage Grotesque", body_font="Inter"),
        mood="grounded", layout_variant="editorial_classic",
        rationale="x" * 30,
    )

    html_a = render_html(_minimal_content("aa", refined))
    html_b = render_html(_minimal_content("bb", grounded))

    # Colors injected
    assert "#14213D" in html_a and "#14213D" not in html_b
    assert "#A04C2D" in html_b and "#A04C2D" not in html_a

    # Fonts wired into Google Fonts URL
    assert "Fraunces" in html_a and "Fraunces" not in html_b
    assert "Bricolage" in html_b and "Bricolage" not in html_a
