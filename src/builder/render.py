"""Jinja2 renderer. Takes a validated SiteContent → HTML file on disk.

Each render uses the BrandDNA (palette + typography + layout variant) to:
  - Inject a Google Fonts <link> matching the picked display + body fonts
  - Drive every color via CSS custom properties (--bg, --primary, etc.)
  - Pick the right Jinja template for the layout variant

Result: same skeleton, completely different look per company.
"""

from __future__ import annotations

import colorsys
import urllib.parse
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .brand_agent import DEFAULT_BRAND_DNA
from .config import CONFIG
from .models import BrandDNA, SiteContent


# Map LayoutVariant → template filename. Only one for now; more in Phase 5.5+.
_TEMPLATE_BY_VARIANT = {
    "editorial_classic":     "editorial_classic.html.j2",
    "editorial_asymmetric":  "editorial_classic.html.j2",  # TODO: dedicated template
    "gallery_minimal":       "editorial_classic.html.j2",  # TODO: dedicated template
}


# --- Color helpers ---------------------------------------------------------

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    s = hex_str.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def _lighten(hex_color: str, amount: float) -> str:
    """Move a color towards white by `amount` in HLS. Used for derived shades."""
    r, g, b = _hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    l = max(0.0, min(1.0, l + amount))
    nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
    return _rgb_to_hex(int(nr * 255), int(ng * 255), int(nb * 255))


def _is_dark(hex_color: str) -> bool:
    r, g, b = _hex_to_rgb(hex_color)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return luminance < 128


def derive_design_tokens(brand: BrandDNA) -> dict:
    """Expand the 5-color palette into the ~12 tokens the template needs."""
    p = brand.palette
    dark_bg = _is_dark(p.bg)

    # Footer = a few steps darker than the bg (or lighter on dark themes)
    if dark_bg:
        footer_bg = _lighten(p.bg, -0.04)
        muted_text = _lighten(p.text, 0.10)
    else:
        footer_bg = _lighten(p.bg, -0.45) if not _is_dark(p.text) else _lighten(p.text, -0.10)
        muted_text = _lighten(p.text, 0.40)

    return {
        "color_bg":          p.bg,
        "color_surface":     p.surface,
        "color_text":        p.text,
        "color_primary":     p.primary,
        "color_secondary":   p.secondary,
        "color_text_muted":  muted_text,
        "color_footer_bg":   footer_bg,
        "is_dark_theme":     dark_bg,
    }


# --- Google Fonts URL builder ----------------------------------------------

def build_google_fonts_url(display_font: str, body_font: str) -> str:
    """Build a single <link href> that loads the picked display + body fonts.

    We always request the same weight range (300–700) plus italics — works for
    every font on the approved list.
    """
    families = []
    seen: set[str] = set()
    for f in (display_font, body_font):
        if f in seen:
            continue
        seen.add(f)
        encoded = urllib.parse.quote(f)
        families.append(f"family={encoded}:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400")
    qs = "&".join(families) + "&display=swap"
    return f"https://fonts.googleapis.com/css2?{qs}"


# --- Render -----------------------------------------------------------------

def _make_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(CONFIG.templates_dir)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )


def render_html(content: SiteContent, template_name: str | None = None) -> str:
    """Render SiteContent → HTML string. No file I/O."""
    brand = content.brand or DEFAULT_BRAND_DNA
    tokens = derive_design_tokens(brand)
    fonts_url = build_google_fonts_url(brand.typography.display_font,
                                       brand.typography.body_font)

    template_name = template_name or _TEMPLATE_BY_VARIANT.get(
        brand.layout_variant, "editorial_classic.html.j2"
    )

    env = _make_env()
    template = env.get_template(template_name)
    payload = content.model_dump()
    payload["brand_tokens"] = tokens
    payload["brand"] = brand.model_dump()
    payload["fonts_url"] = fonts_url
    return template.render(**payload)


def render_to_disk(content: SiteContent, output_dir: Path | None = None,
                   template_name: str | None = None) -> Path:
    """Render and write to dist/<slug>/index.html. Returns the path."""
    out_root = output_dir or CONFIG.output_dir
    site_dir = out_root / content.slug
    site_dir.mkdir(parents=True, exist_ok=True)

    html = render_html(content, template_name=template_name)
    out_path = site_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path
