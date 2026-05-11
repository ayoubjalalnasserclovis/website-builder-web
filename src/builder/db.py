"""Storage layer. SQLite by default (zero-setup), Supabase pluggable.

The repo exposes a small surface: upsert_pending, mark_status, get, list_pending,
record_llm_call, total_cost. That's it. Trivial to swap implementations.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

from .config import CONFIG


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS builds (
    slug             TEXT PRIMARY KEY,
    company_name     TEXT NOT NULL,
    status           TEXT NOT NULL,           -- pending | building | rendered | qa_passed | qa_rejected | failed
    content_json     TEXT,                    -- the validated SiteContent as JSON
    html_path        TEXT,                    -- local path to dist/<slug>/index.html
    deployed_url     TEXT,                    -- filled in Phase 3
    llm_cost_usd     REAL DEFAULT 0,
    error            TEXT,
    qa_score         INTEGER,                 -- 0-10, NULL if not QA'd yet
    qa_verdict       TEXT,                    -- 'pass' | 'reject' | NULL
    qa_findings      TEXT,                    -- JSON array of {severity, area, description}
    qa_screenshot    TEXT,                    -- local path to QA screenshot
    qa_at            TEXT,                    -- timestamp of last QA pass
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_builds_status ON builds(status);

-- Migrations: ALTER TABLE for existing dbs (idempotent via IF NOT EXISTS sentinels in code)
CREATE TABLE IF NOT EXISTS llm_calls (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    slug             TEXT,
    model            TEXT,
    input_tokens     INTEGER,
    output_tokens    INTEGER,
    cost_usd         REAL,
    occurred_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_slug ON llm_calls(slug);
"""

# Forward-compat ALTER columns for users who already have a Phase 0-3 DB.
# SQLite ignores columns that already exist via PRAGMA + try/except in _init_schema.
_QA_COLUMNS = [
    ("qa_score", "INTEGER"),
    ("qa_verdict", "TEXT"),
    ("qa_findings", "TEXT"),
    ("qa_screenshot", "TEXT"),
    ("qa_at", "TEXT"),
]

# Phase 6 — email tracking. Idempotent ALTER for upgrading DBs.
_EMAIL_COLUMNS = [
    ("email_target",       "TEXT"),     # the address we sent to
    ("email_subject",      "TEXT"),     # subject we used
    ("email_body_html",    "TEXT"),     # full body we pushed
    ("email_sent_at",      "TEXT"),     # ISO timestamp
    ("email_provider",     "TEXT"),     # 'instantly'
    ("email_lead_id",      "TEXT"),     # provider lead/contact id (for tracking)
    ("email_error",        "TEXT"),
]

STALE_BUILDING_MINUTES = 5


@dataclass
class BuildRow:
    slug: str
    company_name: str
    status: str
    content_json: Optional[str]
    html_path: Optional[str]
    deployed_url: Optional[str]
    llm_cost_usd: float
    error: Optional[str]
    qa_score: Optional[int]
    qa_verdict: Optional[str]
    qa_findings: Optional[str]
    qa_screenshot: Optional[str]
    qa_at: Optional[str]
    email_target: Optional[str] = None
    email_subject: Optional[str] = None
    email_body_html: Optional[str] = None
    email_sent_at: Optional[str] = None
    email_provider: Optional[str] = None
    email_lead_id: Optional[str] = None
    email_error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class BuildsRepo:
    def __init__(self, db_path: Path | None = None):
        self.path = db_path or CONFIG.db_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(SQLITE_SCHEMA)
            # Idempotent ALTER for users upgrading from earlier phases
            existing = {r[1] for r in c.execute("PRAGMA table_info(builds)").fetchall()}
            for col, col_type in _QA_COLUMNS + _EMAIL_COLUMNS:
                if col not in existing:
                    c.execute(f"ALTER TABLE builds ADD COLUMN {col} {col_type}")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # WAL + busy_timeout enable safe concurrent writes from multiple workers.
        # Without these, SQLite throws 'database is locked' under Semaphore(5+).
        conn = sqlite3.connect(str(self.path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")     # writers don't block readers
        conn.execute("PRAGMA busy_timeout = 5000")    # auto-retry on lock for 5s
        conn.execute("PRAGMA synchronous = NORMAL")   # WAL-safe, much faster
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- Builds ----

    def upsert_pending(self, slug: str, company_name: str) -> None:
        """Insert a new prospect as 'pending'. If exists with status=rendered, no-op."""
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO builds (slug, company_name, status)
                VALUES (?, ?, 'pending')
                ON CONFLICT(slug) DO NOTHING
                """,
                (slug, company_name),
            )

    def mark_building(self, slug: str) -> bool:
        """Try to claim a slug for building. Returns True if claimed.

        Atomic: only allows transition from pending → building, OR from
        a 'building' that's stale (older than STALE_BUILDING_MINUTES).
        Lets the next run resume crashed prospects.
        """
        cutoff = (datetime.utcnow() - timedelta(minutes=STALE_BUILDING_MINUTES)).isoformat()
        with self._conn() as c:
            cur = c.execute(
                """
                UPDATE builds
                SET status = 'building',
                    updated_at = CURRENT_TIMESTAMP,
                    error = NULL
                WHERE slug = ?
                  AND (
                       status = 'pending'
                    OR status = 'failed'
                    OR (status = 'building' AND updated_at < ?)
                  )
                """,
                (slug, cutoff),
            )
            return cur.rowcount > 0

    def mark_rendered(self, slug: str, content_json: str, html_path: str,
                      llm_cost_usd: float) -> None:
        with self._conn() as c:
            c.execute(
                """
                UPDATE builds
                SET status = 'rendered',
                    content_json = ?,
                    html_path = ?,
                    llm_cost_usd = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    error = NULL
                WHERE slug = ?
                """,
                (content_json, html_path, llm_cost_usd, slug),
            )

    def mark_failed(self, slug: str, error: str) -> None:
        with self._conn() as c:
            c.execute(
                """
                UPDATE builds
                SET status = 'failed',
                    error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE slug = ?
                """,
                (error[:2000], slug),
            )

    def get(self, slug: str) -> Optional[BuildRow]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM builds WHERE slug = ?", (slug,)).fetchone()
            if row:
                return BuildRow(**dict(row))
        return None

    def is_done(self, slug: str) -> bool:
        row = self.get(slug)
        return row is not None and row.status == "rendered"

    def list_pending(self) -> list[BuildRow]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM builds WHERE status IN ('pending', 'failed') "
                "ORDER BY created_at ASC"
            ).fetchall()
            return [BuildRow(**dict(r)) for r in rows]

    def list_rendered(self) -> list[BuildRow]:
        """Sites that built successfully (deployed or not)."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM builds WHERE status = 'rendered' "
                "ORDER BY updated_at DESC"
            ).fetchall()
            return [BuildRow(**dict(r)) for r in rows]

    def set_deployed_url(self, slug: str, url: str) -> None:
        """Mark a built site as deployed, store its public URL."""
        with self._conn() as c:
            c.execute(
                "UPDATE builds "
                "SET deployed_url = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE slug = ? AND status IN ('rendered', 'qa_passed')",
                (url, slug),
            )

    # ---- QA (Phase 4) ----

    def list_for_qa(self) -> list[BuildRow]:
        """Sites that should be QA'd: rendered (never QA'd) or qa_rejected (re-check)."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM builds WHERE status IN ('rendered', 'qa_rejected') "
                "ORDER BY updated_at ASC"
            ).fetchall()
            return [BuildRow(**dict(r)) for r in rows]

    def list_deployable(self) -> list[BuildRow]:
        """Sites the deployer should publish: rendered (no QA run) or qa_passed."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM builds WHERE status IN ('rendered', 'qa_passed') "
                "ORDER BY updated_at DESC"
            ).fetchall()
            return [BuildRow(**dict(r)) for r in rows]

    def list_qa_rejected(self) -> list[BuildRow]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM builds WHERE status = 'qa_rejected' "
                "ORDER BY updated_at DESC"
            ).fetchall()
            return [BuildRow(**dict(r)) for r in rows]

    # ---- Email (Phase 6) ----

    def list_deployed_unsent(self, limit: int | None = None) -> list[BuildRow]:
        """Sites that are deployed (deployed_url present) and email never sent."""
        sql = (
            "SELECT * FROM builds "
            "WHERE deployed_url IS NOT NULL AND deployed_url != '' "
            "AND (email_sent_at IS NULL OR email_sent_at = '') "
            "AND (email_error IS NULL OR email_error = '') "
            "ORDER BY updated_at ASC"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._conn() as c:
            rows = c.execute(sql).fetchall()
            return [BuildRow(**dict(r)) for r in rows]

    def record_email_sent(self, slug: str, target: str, subject: str,
                          body_html: str, provider: str, lead_id: str) -> None:
        with self._conn() as c:
            c.execute(
                """
                UPDATE builds
                SET email_target  = ?,
                    email_subject = ?,
                    email_body_html = ?,
                    email_provider = ?,
                    email_lead_id  = ?,
                    email_sent_at  = CURRENT_TIMESTAMP,
                    email_error    = NULL,
                    updated_at     = CURRENT_TIMESTAMP
                WHERE slug = ?
                """,
                (target, subject, body_html, provider, lead_id, slug),
            )

    def record_email_failure(self, slug: str, error: str) -> None:
        with self._conn() as c:
            c.execute(
                """
                UPDATE builds
                SET email_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE slug = ?
                """,
                (error[:2000], slug),
            )

    def record_qa_result(self, slug: str, score: int, verdict: str,
                         findings_json: str, screenshot_path: str) -> None:
        """Apply the QA outcome and transition the status atomically.
        verdict='pass' → status='qa_passed'. verdict='reject' → 'qa_rejected'.
        """
        new_status = "qa_passed" if verdict == "pass" else "qa_rejected"
        with self._conn() as c:
            c.execute(
                """
                UPDATE builds
                SET status = ?,
                    qa_score = ?,
                    qa_verdict = ?,
                    qa_findings = ?,
                    qa_screenshot = ?,
                    qa_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE slug = ?
                """,
                (new_status, score, verdict, findings_json, screenshot_path, slug),
            )

    # ---- LLM calls ----

    def record_llm_call(self, slug: str, model: str,
                        input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO llm_calls (slug, model, input_tokens, output_tokens, cost_usd)
                VALUES (?, ?, ?, ?, ?)
                """,
                (slug, model, input_tokens, output_tokens, cost_usd),
            )

    def total_cost_usd(self) -> float:
        with self._conn() as c:
            row = c.execute("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM llm_calls").fetchone()
            return float(row["total"])

    def stats(self) -> dict:
        with self._conn() as c:
            counts = {r["status"]: r["n"] for r in c.execute(
                "SELECT status, COUNT(*) AS n FROM builds GROUP BY status"
            )}
            cost = self.total_cost_usd()
            return {"counts": counts, "total_cost_usd": round(cost, 4)}
