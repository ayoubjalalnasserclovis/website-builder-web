"""CLI for QA review of built sites.

Usage:
    # Review all `rendered` and `qa_rejected` sites
    python scripts/qa.py

    # Review a single slug
    python scripts/qa.py --slug influence-patrimoine

    # See list of currently rejected sites (read-only)
    python scripts/qa.py --list-rejected

Pre-requisites:
    pip install -e .[qa]
    playwright install chromium
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import json

import typer
from rich.console import Console
from rich.table import Table

from builder.db import BuildsRepo
from builder.qa_agent import review_batch_sync

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    slug: str = typer.Option(None, "--slug", help="QA un seul slug spécifique"),
    list_rejected: bool = typer.Option(False, "--list-rejected",
                                        help="Affiche les sites en qa_rejected (sans relancer)"),
):
    repo = BuildsRepo()

    if list_rejected:
        rows = repo.list_qa_rejected()
        if not rows:
            console.print("[green]Aucun site en qa_rejected.[/]")
            raise typer.Exit(0)

        table = Table(title=f"{len(rows)} sites en qa_rejected", header_style="bold yellow")
        table.add_column("slug")
        table.add_column("score")
        table.add_column("findings (résumé)", overflow="fold")
        for r in rows:
            findings = []
            try:
                findings = json.loads(r.qa_findings or "[]")
            except json.JSONDecodeError:
                pass
            critical = [f for f in findings if f.get("severity") == "critical"]
            findings_summary = (
                f"[red]{len(critical)} critical[/] · "
                f"{len(findings) - len(critical)} other"
            )
            table.add_row(r.slug, str(r.qa_score or "—"), findings_summary)
        console.print(table)
        raise typer.Exit(0)

    results = review_batch_sync(only_slug=slug)
    if not results:
        raise typer.Exit(0)

    failed_results = [r for r in results if not r.ok]
    if failed_results:
        console.print(f"\n[yellow]{len(failed_results)} runs en erreur :[/]")
        for r in failed_results:
            console.print(f"  • {r.slug}: {r.error}")


if __name__ == "__main__":
    app()
