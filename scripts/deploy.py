"""CLI for deploying built sites to Cloudflare Pages.

Usage:
    # Run pre-flight check only (no deploy)
    python scripts/deploy.py --check

    # Deploy everything in dist/ to the configured project
    python scripts/deploy.py

    # Override config from CLI
    python scripts/deploy.py --project demos --base-url https://demos.tondomaine.fr

Pre-requisites (one-time):
    npm install -g wrangler
    Set CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_PAGES_PROJECT
    in .env (see .env.example).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `src/` importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import typer
from rich.console import Console
from rich.table import Table

from builder.deployer import DeployError, deploy, preflight

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    dist: Path = typer.Option(None, "--dist", help="Dossier à déployer (défaut: ./dist)"),
    project: str = typer.Option(None, "--project", help="Nom du projet Pages"),
    base_url: str = typer.Option(None, "--base-url",
                                  help="URL publique de base. Ex: https://demos.tondomaine.fr"),
    check: bool = typer.Option(False, "--check",
                                help="Pre-flight check uniquement, ne déploie pas"),
    no_qa_strict: bool = typer.Option(False, "--no-qa-strict",
                                       help="Publie tout dist/, sans filtrer par statut QA"),
):
    if check:
        issues = preflight()
        if not issues:
            console.print("[green bold]✓ Pre-flight OK.[/] Prêt à déployer.")
            raise typer.Exit(0)
        console.print("[red bold]✗ Pre-flight a trouvé des problèmes :[/]")
        for issue in issues:
            console.print(f"  • {issue}")
        raise typer.Exit(1)

    try:
        result = deploy(
            dist_dir=dist,
            project_name=project,
            public_base_url=base_url,
            qa_strict=not no_qa_strict,
        )
    except DeployError as e:
        console.print(f"\n[red bold]Deploy échoué :[/]\n{e}")
        raise typer.Exit(1)

    console.print(
        f"\n[bold green]✓ {len(result.deployed_slugs)} sites déployés[/]"
    )
    if result.created_project:
        console.print(f"  [dim](projet '{result.project_name}' créé à la volée)[/]")

    table = Table(title="URLs publiques", show_header=True, header_style="bold cyan")
    table.add_column("Slug")
    table.add_column("URL")
    for slug in result.deployed_slugs[:20]:
        table.add_row(slug, f"{result.public_base_url}/{slug}/")
    console.print(table)
    if len(result.deployed_slugs) > 20:
        console.print(f"... et {len(result.deployed_slugs) - 20} autres "
                      f"(vois la table 'builds' en DB pour la liste complète)")


if __name__ == "__main__":
    app()
