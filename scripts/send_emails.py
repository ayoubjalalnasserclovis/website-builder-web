"""CLI for sending cold emails to deployed prospects via Instantly.

Usage:
    # Pre-flight check
    python scripts/send_emails.py --check

    # Dry-run: generate emails but don't send
    python scripts/send_emails.py --dry-run --limit 3

    # Real send
    python scripts/send_emails.py --limit 50

    # Inspect: see prospects ready to be emailed
    python scripts/send_emails.py --list-pending

Pre-requisites (one-time):
    1. Create a campaign in Instantly UI:
       - Set up sending email account(s) with warm-up done
       - Add a sequence with subject = {{personalization.subject}}
         and body = {{personalization.body_html}}
       - Save and grab the campaign ID
    2. Fill in .env:
       INSTANTLY_API_KEY, INSTANTLY_CAMPAIGN_ID, SENDER_* fields
    3. Make sure your prospects have status='deployed' (run build → deploy first)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import typer
from rich.console import Console
from rich.table import Table

from builder.db import BuildsRepo
from builder.email_sender import is_business_email, send_batch_sync
from builder.instantly_client import preflight as instantly_preflight

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    limit: int = typer.Option(None, "--limit", "-n",
                              help="Cap on number of emails to send this run"),
    concurrency: int = typer.Option(4, "--concurrency", "-c"),
    dry_run: bool = typer.Option(False, "--dry-run",
                                  help="Generate emails but don't push to Instantly"),
    check: bool = typer.Option(False, "--check",
                                help="Pre-flight only — verify config + campaign"),
    list_pending: bool = typer.Option(False, "--list-pending",
                                       help="Show prospects ready to be emailed (read-only)"),
):
    if check:
        issues = instantly_preflight()
        if not issues:
            console.print("[green bold]✓ Pre-flight OK.[/] Prêt à envoyer des cold emails.")
            raise typer.Exit(0)
        console.print("[red bold]✗ Pre-flight a trouvé des problèmes :[/]")
        for issue in issues:
            console.print(f"  • {issue}")
        raise typer.Exit(1)

    if list_pending:
        repo = BuildsRepo()
        rows = repo.list_deployed_unsent()
        if not rows:
            console.print("[dim]Aucun prospect en attente d'envoi.[/]")
            raise typer.Exit(0)

        table = Table(title=f"{len(rows)} prospects à contacter",
                       header_style="bold cyan")
        table.add_column("slug")
        table.add_column("entreprise")
        table.add_column("email cible")
        table.add_column("RGPD ok ?")
        table.add_column("URL démo", overflow="fold")
        for r in rows[:50]:
            email = ""
            try:
                import json
                content = json.loads(r.content_json or "{}")
                email = content.get("branding", {}).get("email", "")
            except json.JSONDecodeError:
                pass
            ok = is_business_email(email)
            ok_label = "[green]oui[/]" if ok else (
                "[red]non[/] (perso)" if email else "[red]non[/] (vide)"
            )
            table.add_row(r.slug, r.company_name, email or "—", ok_label,
                          r.deployed_url or "—")
        console.print(table)
        if len(rows) > 50:
            console.print(f"... et {len(rows) - 50} autres")
        raise typer.Exit(0)

    try:
        results = send_batch_sync(limit=limit, concurrency=concurrency, dry_run=dry_run)
    except RuntimeError as e:
        console.print(f"[red bold]Échec :[/] {e}")
        raise typer.Exit(1)

    failed = [r for r in results if not r.ok and not r.skipped]
    if failed:
        console.print(f"\n[yellow]{len(failed)} envois en erreur :[/]")
        for r in failed:
            console.print(f"  • {r.slug}: {r.error}")


if __name__ == "__main__":
    app()
