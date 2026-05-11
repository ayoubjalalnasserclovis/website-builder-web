"""Cold email orchestrator.

Per prospect (status=deployed, not yet emailed):
  1. RGPD pre-flight: refuse personal email domains (gmail, yahoo, free…)
     for B2B cold outreach. Only pro/business domains pass.
  2. Reload the SiteContent + BrandDNA from DB
  3. Generate the email via EmailAgent (uses skills/cold_email_writer.md)
  4. Push to Instantly as a personalized lead in the configured campaign
  5. Update DB: email_sent_at, email_lead_id, email_subject, email_body_html

If any step fails, we record email_error and skip — re-runnable, idempotent.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Optional

from rich.console import Console

from .config import CONFIG
from .db import BuildRow, BuildsRepo
from .email_agent import EmailAgent
from .instantly_client import (
    InstantlyError,
    add_lead_to_campaign,
    preflight as instantly_preflight,
)
from .llm import LLM
from .models import (
    BrandDNA,
    ColdEmail,
    ProspectInput,
    SenderIdentity,
    SiteContent,
)

console = Console()

# Personal-email domains that we MUST NOT cold email (RGPD: B2B only).
# This is the ironclad rule: B2B cold email is allowed under "intérêt légitime"
# only when the recipient is a professional. A gmail address is presumed personal.
PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.fr", "hotmail.com", "hotmail.fr",
    "outlook.com", "outlook.fr", "live.com", "live.fr",
    "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr", "laposte.net",
    "neuf.fr", "alice.fr", "club-internet.fr", "9online.fr",
    "icloud.com", "me.com", "aol.com", "msn.com", "protonmail.com",
    "proton.me", "mailfence.com", "tutanota.com", "gmx.fr", "gmx.com",
}

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


# --- RGPD pre-flight per prospect ------------------------------------------

def is_business_email(email: str) -> bool:
    """True if email looks like a professional address. False = personal/invalid."""
    if not email or not _EMAIL_RE.match(email):
        return False
    domain = email.split("@", 1)[1].lower()
    return domain not in PERSONAL_EMAIL_DOMAINS


def extract_first_name(email: str | None) -> str:
    """Best-effort first-name extraction from email like firstname.lastname@domain."""
    if not email or "@" not in email:
        return ""
    local = email.split("@", 1)[0]
    parts = re.split(r"[._-]", local)
    if not parts or len(parts[0]) < 2:
        return ""
    candidate = parts[0]
    # Reject obvious non-names (contact, info, hello, etc.)
    NON_NAMES = {"contact", "info", "hello", "bonjour", "admin", "office",
                 "support", "sales", "team", "no-reply", "noreply"}
    if candidate.lower() in NON_NAMES:
        return ""
    if any(c.isdigit() for c in candidate):
        return ""
    return candidate.capitalize()


# --- Sender identity from .env ---------------------------------------------

def sender_from_config() -> SenderIdentity:
    return SenderIdentity(
        name=CONFIG.sender_name,
        role=CONFIG.sender_role,
        company=CONFIG.sender_company,
        siren=CONFIG.sender_siren,
        address=CONFIG.sender_address,
        phone=CONFIG.sender_phone or None,
        reply_to_email=CONFIG.sender_reply_to,
    )


# --- Result ----------------------------------------------------------------

@dataclass
class SendResult:
    slug: str
    ok: bool
    skipped: Optional[str] = None      # reason: 'personal_email', 'no_email', etc.
    lead_id: Optional[str] = None
    error: Optional[str] = None


# --- Send one prospect -----------------------------------------------------

def send_one(build: BuildRow, agent: EmailAgent | None = None,
             sender: SenderIdentity | None = None,
             repo: BuildsRepo | None = None,
             dry_run: bool = False) -> SendResult:
    repo = repo or BuildsRepo()
    sender = sender or sender_from_config()
    agent = agent or EmailAgent()

    if not build.deployed_url:
        return SendResult(slug=build.slug, ok=False, skipped="not_deployed")
    if not build.content_json:
        return SendResult(slug=build.slug, ok=False, skipped="no_content_json")

    try:
        site_data = json.loads(build.content_json)
    except json.JSONDecodeError as e:
        return SendResult(slug=build.slug, ok=False, error=f"bad content_json: {e}")

    target_email = (site_data.get("branding") or {}).get("email", "").strip().lower()

    # --- RGPD gate ---
    if not target_email:
        repo.record_email_failure(build.slug, "no email on prospect")
        return SendResult(slug=build.slug, ok=False, skipped="no_email")
    if not is_business_email(target_email):
        repo.record_email_failure(build.slug,
                                  f"personal email domain — refused for RGPD: {target_email}")
        return SendResult(slug=build.slug, ok=False, skipped="personal_email")

    # --- Re-hydrate models ---
    try:
        content = SiteContent.model_validate(site_data)
    except Exception as e:
        return SendResult(slug=build.slug, ok=False, error=f"SiteContent validation: {e}")
    brand: BrandDNA | None = content.brand
    if brand is None:
        return SendResult(slug=build.slug, ok=False,
                          error="content has no brand DNA, cannot adapt tone")

    prospect = ProspectInput(
        slug=build.slug,
        company_name=build.company_name,
        source_text="",  # we don't store the original source_text per-row currently
        email=target_email,
        sector_hint=content.sector,
    )

    # --- Generate email ---
    try:
        email: ColdEmail = agent.generate(
            prospect=prospect,
            content=content,
            brand=brand,
            sender=sender,
            demo_url=build.deployed_url,
        )
    except Exception as e:
        repo.record_email_failure(build.slug, f"agent: {e}")
        return SendResult(slug=build.slug, ok=False, error=str(e))

    if dry_run:
        console.print(f"[yellow][dry-run][/] would send to {target_email}: "
                      f"subject=\"{email.subject}\"")
        return SendResult(slug=build.slug, ok=True, lead_id="dry-run")

    # --- Push to Instantly ---
    first_name = extract_first_name(target_email)
    personalization = {
        "subject":   email.subject,
        "preheader": email.preheader,
        "body_html": email.body_html,
        "body_text": email.body_text,
        "demo_url":  build.deployed_url,
    }
    try:
        result = add_lead_to_campaign(
            campaign_id=CONFIG.instantly_campaign_id,
            email=target_email,
            company_name=build.company_name,
            first_name=first_name,
            personalization=personalization,
        )
    except InstantlyError as e:
        repo.record_email_failure(build.slug, f"instantly: {e}")
        return SendResult(slug=build.slug, ok=False, error=str(e))

    repo.record_email_sent(
        slug=build.slug,
        target=target_email,
        subject=email.subject,
        body_html=email.body_html,
        provider="instantly",
        lead_id=result.lead_id,
    )
    console.print(f"[green]✓[/] {build.slug}: pushed to Instantly "
                  f"(target={target_email}, lead_id={result.lead_id})")
    return SendResult(slug=build.slug, ok=True, lead_id=result.lead_id)


# --- Batch -----------------------------------------------------------------

async def send_batch_async(limit: int | None = None,
                           concurrency: int = 4,
                           dry_run: bool = False) -> list[SendResult]:
    issues = instantly_preflight()
    if issues:
        raise RuntimeError(
            "Pre-flight failed:\n  - " + "\n  - ".join(issues)
        )

    repo = BuildsRepo()
    targets = repo.list_deployed_unsent(limit=limit)
    if not targets:
        console.print("[dim]No prospects to email (all deployed sites already contacted "
                      "or in error state).[/]")
        return []

    console.print(f"[bold]Sending cold emails to {len(targets)} prospects "
                  f"(concurrency={concurrency}, dry_run={dry_run})[/]")

    sem = asyncio.Semaphore(concurrency)
    sender = sender_from_config()
    agent = EmailAgent(llm=LLM(model=CONFIG.model_content,
                               fallback=CONFIG.model_content_fallback))

    async def worker(b: BuildRow) -> SendResult:
        async with sem:
            return await asyncio.to_thread(send_one, b, agent, sender, repo, dry_run)

    coros = [worker(b) for b in targets]
    results: list[SendResult] = []
    for fut in asyncio.as_completed(coros):
        results.append(await fut)

    sent = sum(1 for r in results if r.ok and r.lead_id != "dry-run")
    skipped = sum(1 for r in results if r.skipped)
    failed = sum(1 for r in results if not r.ok and not r.skipped)
    dry = sum(1 for r in results if r.lead_id == "dry-run")
    console.print(
        f"\n[bold]Done.[/] sent={sent} dry_run={dry} skipped={skipped} failed={failed} "
        f"cost=${agent.llm.usage.cost_snapshot():.4f}"
    )
    return results


def send_batch_sync(limit: int | None = None, concurrency: int = 4,
                    dry_run: bool = False) -> list[SendResult]:
    return asyncio.run(send_batch_async(limit=limit, concurrency=concurrency,
                                        dry_run=dry_run))
