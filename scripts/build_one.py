"""CLI to build a single site.

Usage:
    python scripts/build_one.py \\
        --name "Influence Patrimoine" \\
        --slug influence-patrimoine \\
        --text-file source.txt \\
        --sector wealth_management \\
        --phone "09 81 94 88 08" \\
        --phone-tel "+33981948808" \\
        --email contact@influence-patrimoine.fr
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `src/` importable when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import typer
from rich.console import Console

from builder.batch import slugify
from builder.builder import build_one
from builder.models import ProspectInput

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    name: str = typer.Option(..., "--name", help="Nom de l'entreprise"),
    slug: str = typer.Option("", "--slug", help="Slug URL (auto-généré si vide)"),
    text: str = typer.Option("", "--text", help="Texte source brut"),
    text_file: Path = typer.Option(None, "--text-file", help="Fichier texte source"),
    sector: str = typer.Option(None, "--sector", help="Secteur (cf. models.py)"),
    phone: str = typer.Option(None, "--phone", help="Téléphone affichage"),
    phone_tel: str = typer.Option(None, "--phone-tel", help="Téléphone format tel:"),
    email: str = typer.Option(None, "--email", help="Email"),
    hero_image: str = typer.Option(None, "--hero-image", help="URL d'image hero (override)"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    if text_file and not text:
        text = text_file.read_text(encoding="utf-8")

    prospect = ProspectInput(
        slug=slug or slugify(name),
        company_name=name,
        source_text=text,
        sector_hint=sector,
        phone=phone,
        phone_tel=phone_tel,
        email=email,
        hero_image_url=hero_image,
    )

    console.print(f"[bold]Building site for[/] {name} (slug: {prospect.slug})")
    result = build_one(prospect, dry_run=dry_run)

    if result.ok:
        console.print(f"\n[green bold]Success.[/] HTML: {result.html_path}")
        console.print(f"Cost: ${result.cost_usd:.4f}")
        raise typer.Exit(0)
    else:
        console.print(f"\n[red bold]Failed:[/] {result.error}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
