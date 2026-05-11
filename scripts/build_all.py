"""CLI for mass build from a CSV.

Usage:
    python scripts/build_all.py prospects.csv
    python scripts/build_all.py prospects.csv --concurrency 10 --budget 5
    python scripts/build_all.py prospects.csv --dry-run
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import typer
from rich.console import Console
from rich.table import Table

from builder.batch import build_all_sync, parse_csv
from builder.db import BuildsRepo

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    csv_path: Path = typer.Argument(..., exists=True, readable=True,
                                    help="Chemin du CSV de prospects"),
    concurrency: int = typer.Option(None, "--concurrency", "-c"),
    budget: float = typer.Option(None, "--budget", "-b",
                                 help="Plafond LLM en USD (override .env)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Aucun appel API"),
):
    prospects = parse_csv(csv_path)
    console.print(f"[bold]Loaded {len(prospects)} prospects from {csv_path}[/]\n")

    if not prospects:
        console.print("[yellow]Nothing to do.[/]")
        raise typer.Exit(0)

    results = build_all_sync(
        prospects,
        max_concurrency=concurrency,
        max_budget_usd=budget,
        dry_run=dry_run,
    )

    # Pretty stats from the DB
    repo = BuildsRepo()
    stats = repo.stats()
    table = Table(title="Build status")
    table.add_column("status")
    table.add_column("count", justify="right")
    for status, n in stats["counts"].items():
        table.add_row(status, str(n))
    console.print(table)
    console.print(f"\nTotal LLM cost (cumulative across runs): "
                  f"[bold]${stats['total_cost_usd']:.4f}[/]")


if __name__ == "__main__":
    app()
