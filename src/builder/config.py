"""Centralized config loading. One place to look for env vars."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env file once at import
load_dotenv()


@dataclass(frozen=True)
class Config:
    # LLM
    openrouter_api_key: str
    model_content: str
    model_content_fallback: str
    model_qa: str

    # DB
    db_backend: str        # "sqlite" or "supabase"
    db_path: Path
    supabase_url: str
    supabase_key: str

    # Build
    max_concurrency: int
    max_budget_usd: float
    output_dir: Path
    templates_dir: Path

    # QA (Phase 4)
    qa_score_threshold: int
    qa_viewport_width: int
    qa_viewport_height: int
    qa_screenshots_dir: Path
    qa_concurrency: int

    # Cloudflare Pages (Phase 3 — deploy)
    cf_api_token: str
    cf_account_id: str
    cf_pages_project: str
    public_base_url: str   # e.g. "https://demos.tondomaine.fr". Falls back to *.pages.dev

    # Cold email (Phase 6 — Instantly + sender identity for RGPD)
    instantly_api_key: str
    instantly_campaign_id: str
    instantly_base_url: str
    sender_name: str
    sender_role: str
    sender_company: str
    sender_siren: str
    sender_address: str
    sender_phone: str
    sender_reply_to: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            model_content=os.getenv("LLM_MODEL_CONTENT", "anthropic/claude-3.5-haiku"),
            model_content_fallback=os.getenv("LLM_MODEL_CONTENT_FALLBACK", "openai/gpt-4o-mini"),
            model_qa=os.getenv("LLM_MODEL_QA", "google/gemini-2.5-flash"),
            db_backend=os.getenv("DB_BACKEND", "sqlite").lower(),
            db_path=Path(os.getenv("DB_PATH", "./prospects.db")),
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_key=os.getenv("SUPABASE_KEY", ""),
            max_concurrency=int(os.getenv("MAX_CONCURRENCY", "5")),
            max_budget_usd=float(os.getenv("MAX_BUDGET_USD", "10.0")),
            output_dir=Path(os.getenv("OUTPUT_DIR", "./dist")),
            templates_dir=Path(os.getenv("TEMPLATES_DIR", "./templates")),
            qa_score_threshold=int(os.getenv("QA_SCORE_THRESHOLD", "7")),
            qa_viewport_width=int(os.getenv("QA_VIEWPORT_WIDTH", "1440")),
            qa_viewport_height=int(os.getenv("QA_VIEWPORT_HEIGHT", "900")),
            qa_screenshots_dir=Path(os.getenv("QA_SCREENSHOTS_DIR", "./qa_screenshots")),
            qa_concurrency=int(os.getenv("QA_CONCURRENCY", "3")),
            cf_api_token=os.getenv("CLOUDFLARE_API_TOKEN", ""),
            cf_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
            cf_pages_project=os.getenv("CLOUDFLARE_PAGES_PROJECT", ""),
            public_base_url=os.getenv("PUBLIC_BASE_URL", "").rstrip("/"),
            instantly_api_key=os.getenv("INSTANTLY_API_KEY", ""),
            instantly_campaign_id=os.getenv("INSTANTLY_CAMPAIGN_ID", ""),
            instantly_base_url=os.getenv("INSTANTLY_BASE_URL",
                                         "https://api.instantly.ai/api/v2"),
            sender_name=os.getenv("SENDER_NAME", ""),
            sender_role=os.getenv("SENDER_ROLE", ""),
            sender_company=os.getenv("SENDER_COMPANY", ""),
            sender_siren=os.getenv("SENDER_SIREN", ""),
            sender_address=os.getenv("SENDER_ADDRESS", ""),
            sender_phone=os.getenv("SENDER_PHONE", ""),
            sender_reply_to=os.getenv("SENDER_REPLY_TO", ""),
        )


# Singleton
CONFIG = Config.from_env()
