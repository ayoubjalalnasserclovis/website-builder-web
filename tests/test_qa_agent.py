"""Tests for the QA agent.

Covers:
  - Business rule: pass/reject derivation from score + findings
  - DB transitions on QA result
  - QAAgent.review() with mocked screenshot + mocked vision LLM
  - Schema validation rejects malformed LLM output
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from builder.db import BuildRow, BuildsRepo
from builder.models import QAFinding, QAReport
from builder.qa_agent import QAAgent, QAResult, _enforce_verdict


# --- Business rule ----------------------------------------------------------

def test_enforce_verdict_passes_when_score_high_and_no_critical():
    report = QAReport(
        score=8, verdict="pass",
        summary="Site très bon, quelques accrocs mineurs sans gravité.",
        findings=[QAFinding(severity="minor", area="layout",
                            description="Espacement légèrement serré sur mobile")],
    )
    assert _enforce_verdict(report, threshold=7) == "pass"


def test_enforce_verdict_rejects_when_below_threshold():
    report = QAReport(
        score=5, verdict="pass",  # LLM said pass but business rule disagrees
        summary="Site moyen avec problèmes notables à corriger en priorité.",
        findings=[],
    )
    assert _enforce_verdict(report, threshold=7) == "reject"


def test_enforce_verdict_rejects_on_critical_even_if_score_high():
    """A critical finding always rejects, regardless of score."""
    report = QAReport(
        score=9, verdict="pass",
        summary="Site bon dans l'ensemble mais image hero cassée bloque l'envoi.",
        findings=[QAFinding(severity="critical", area="image",
                            description="Image hero affiche une zone grise (404 ?)")],
    )
    assert _enforce_verdict(report, threshold=7) == "reject"


def test_enforce_verdict_does_not_blindly_trust_llm():
    """Even if LLM says reject, we still re-derive from rules."""
    report = QAReport(
        score=10, verdict="reject",  # LLM disagrees with itself
        summary="Site impeccable, signé Hermès. Aucun reproche possible.",
        findings=[],
    )
    assert _enforce_verdict(report, threshold=7) == "pass"


# --- Pydantic schema validation ---------------------------------------------

def test_qareport_rejects_score_above_10():
    with pytest.raises(ValidationError):
        QAReport(score=11, verdict="pass", summary="x" * 30)


def test_qareport_rejects_invalid_verdict():
    with pytest.raises(ValidationError):
        QAReport(score=8, verdict="maybe", summary="x" * 30)


def test_qafinding_rejects_invalid_severity():
    with pytest.raises(ValidationError):
        QAFinding(severity="catastrophic", area="layout", description="x" * 20)


# --- DB transitions ---------------------------------------------------------

def test_record_qa_result_transitions_to_qa_passed(tmp_path):
    repo = BuildsRepo(db_path=tmp_path / "test.db")
    repo.upsert_pending("foo", "Foo SARL")
    # Force into 'rendered' state via raw SQL (simulating a successful build)
    with repo._conn() as c:
        c.execute("UPDATE builds SET status='rendered' WHERE slug=?", ("foo",))

    repo.record_qa_result("foo", score=8, verdict="pass",
                          findings_json="[]", screenshot_path="/tmp/foo.jpg")

    row = repo.get("foo")
    assert row.status == "qa_passed"
    assert row.qa_score == 8
    assert row.qa_verdict == "pass"
    assert row.qa_at is not None


def test_record_qa_result_transitions_to_qa_rejected(tmp_path):
    repo = BuildsRepo(db_path=tmp_path / "test.db")
    repo.upsert_pending("bar", "Bar SARL")
    with repo._conn() as c:
        c.execute("UPDATE builds SET status='rendered' WHERE slug=?", ("bar",))

    repo.record_qa_result("bar", score=4, verdict="reject",
                          findings_json='[{"severity":"critical","area":"image","description":"broken"}]',
                          screenshot_path="/tmp/bar.jpg")

    row = repo.get("bar")
    assert row.status == "qa_rejected"
    assert row.qa_score == 4


def test_list_for_qa_finds_rendered_and_rejected(tmp_path):
    repo = BuildsRepo(db_path=tmp_path / "test.db")
    repo.upsert_pending("a", "A SARL")
    repo.upsert_pending("b", "B SARL")
    repo.upsert_pending("c", "C SARL")
    with repo._conn() as c:
        c.execute("UPDATE builds SET status='rendered' WHERE slug='a'")
        c.execute("UPDATE builds SET status='qa_passed' WHERE slug='b'")
        c.execute("UPDATE builds SET status='qa_rejected' WHERE slug='c'")

    slugs = {r.slug for r in repo.list_for_qa()}
    assert slugs == {"a", "c"}  # b is excluded (already passed)


def test_list_deployable_excludes_qa_rejected(tmp_path):
    repo = BuildsRepo(db_path=tmp_path / "test.db")
    repo.upsert_pending("ok1", "X")
    repo.upsert_pending("ok2", "Y")
    repo.upsert_pending("bad", "Z")
    with repo._conn() as c:
        c.execute("UPDATE builds SET status='rendered' WHERE slug='ok1'")
        c.execute("UPDATE builds SET status='qa_passed' WHERE slug='ok2'")
        c.execute("UPDATE builds SET status='qa_rejected' WHERE slug='bad'")

    slugs = {r.slug for r in repo.list_deployable()}
    assert slugs == {"ok1", "ok2"}


# --- QAAgent.review with mocks ---------------------------------------------

@pytest.mark.asyncio
async def test_qa_agent_review_pass_path(tmp_path, monkeypatch):
    """End-to-end of QAAgent.review() with mocked screenshot + mocked LLM."""
    from builder import qa_agent as qa_module

    # Set up DB + a fake build
    db_path = tmp_path / "test.db"
    repo = BuildsRepo(db_path=db_path)
    html_path = tmp_path / "site" / "index.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text("<html></html>")
    repo.upsert_pending("foo", "Foo SARL")
    with repo._conn() as c:
        c.execute(
            "UPDATE builds SET status='rendered', html_path=?, content_json=? WHERE slug=?",
            (str(html_path),
             json.dumps({"sector": "wealth_management"}),
             "foo"),
        )

    # Redirect screenshots dir to a temp location
    screenshots_dir = tmp_path / "screenshots"

    # Mock browser.screenshot to write a fake JPEG and not actually use playwright
    fake_browser = MagicMock()

    async def fake_screenshot(html, out, **kwargs):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")  # not real but enough
        return out

    fake_browser.screenshot = fake_screenshot

    # Mock the LLM vision_json call
    fake_llm = MagicMock()
    fake_llm.model = "google/gemini-2.5-flash"
    fake_llm.vision_json.return_value = json.dumps({
        "score": 8,
        "verdict": "pass",
        "summary": "Site éditorial soigné, typographie premium et hiérarchie claire.",
        "findings": [
            {"severity": "polish", "area": "layout",
             "description": "On pourrait raffiner l'espacement du footer mais rien de bloquant"}
        ],
    })

    agent = qa_module.QAAgent(llm=fake_llm, screenshots_dir=screenshots_dir)

    row = repo.get("foo")
    result = await agent.review(row, fake_browser, repo)

    assert result.ok is True
    assert result.verdict == "pass"
    assert result.score == 8

    # Verify DB was updated
    updated = repo.get("foo")
    assert updated.status == "qa_passed"
    assert updated.qa_score == 8


@pytest.mark.asyncio
async def test_qa_agent_review_reject_path(tmp_path, monkeypatch):
    """A critical finding flips the verdict even if the LLM says pass."""
    from builder import qa_agent as qa_module

    db_path = tmp_path / "test.db"
    repo = BuildsRepo(db_path=db_path)
    html_path = tmp_path / "site" / "index.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text("<html></html>")
    repo.upsert_pending("bar", "Bar SARL")
    with repo._conn() as c:
        c.execute(
            "UPDATE builds SET status='rendered', html_path=?, content_json='{}' WHERE slug=?",
            (str(html_path), "bar"),
        )

    screenshots_dir = tmp_path / "screenshots"

    fake_browser = MagicMock()

    async def fake_screenshot(html, out, **kwargs):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"jpeg")
        return out

    fake_browser.screenshot = fake_screenshot

    fake_llm = MagicMock()
    fake_llm.model = "google/gemini-2.5-flash"
    fake_llm.vision_json.return_value = json.dumps({
        "score": 9,                     # high score
        "verdict": "pass",              # LLM says pass
        "summary": "Site visuellement très réussi malgré l'image hero qui ne charge pas.",
        "findings": [
            {"severity": "critical", "area": "image",  # but critical finding!
             "description": "Image hero affiche une zone grise au lieu de la photo (URL cassée ?)"}
        ],
    })

    agent = qa_module.QAAgent(llm=fake_llm, screenshots_dir=screenshots_dir)
    row = repo.get("bar")
    result = await agent.review(row, fake_browser, repo)

    assert result.ok is True
    assert result.verdict == "reject"   # business rule overrides LLM
    assert result.score == 9

    updated = repo.get("bar")
    assert updated.status == "qa_rejected"


@pytest.mark.asyncio
async def test_qa_agent_handles_invalid_llm_json(tmp_path, monkeypatch):
    """If LLM returns garbage twice, agent reports error and doesn't crash."""
    from builder import qa_agent as qa_module

    db_path = tmp_path / "test.db"
    repo = BuildsRepo(db_path=db_path)
    html_path = tmp_path / "site" / "index.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text("<html></html>")
    repo.upsert_pending("baz", "Baz SARL")
    with repo._conn() as c:
        c.execute("UPDATE builds SET status='rendered', html_path=? WHERE slug=?",
                  (str(html_path), "baz"))

    screenshots_dir = tmp_path / "screenshots"

    fake_browser = MagicMock()

    async def fake_screenshot(html, out, **kwargs):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"jpeg")
        return out

    fake_browser.screenshot = fake_screenshot

    fake_llm = MagicMock()
    fake_llm.model = "google/gemini-2.5-flash"
    # Returns garbage every time
    fake_llm.vision_json.return_value = "this is not json at all, sorry"

    agent = qa_module.QAAgent(llm=fake_llm, screenshots_dir=screenshots_dir)
    row = repo.get("baz")
    result = await agent.review(row, fake_browser, repo)

    assert result.ok is False
    assert "valid QAReport" in (result.error or "")
    # DB status stays at 'rendered' (no QA result was recorded)
    updated = repo.get("baz")
    assert updated.status == "rendered"
