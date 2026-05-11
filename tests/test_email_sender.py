"""Tests for the cold email pipeline.

Covers:
  - RGPD gate: personal email domains are refused
  - Pydantic enforcement of {{unsubscribe_link}} placeholder
  - EmailAgent retry-on-validation loop (mocked LLM)
  - Instantly client error paths (auth fail, campaign 404, lead conflict)
  - DB transitions: list_deployed_unsent, record_email_sent, record_email_failure
  - send_one() end-to-end with mocked agent + mocked Instantly
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from builder.db import BuildRow, BuildsRepo
from builder.email_agent import EmailAgent
from builder.email_sender import (
    extract_first_name,
    is_business_email,
    send_one,
    PERSONAL_EMAIL_DOMAINS,
)
from builder.instantly_client import (
    InstantlyError,
    add_lead_to_campaign,
    preflight as instantly_preflight,
)
from builder.models import (
    ApproachContent,
    BrandDNA,
    Branding,
    ColdEmail,
    ContactContent,
    HeroContent,
    HeroMetric,
    ManifestoContent,
    Palette,
    ProspectInput,
    SenderIdentity,
    Service,
    ServicesContent,
    SiteContent,
    Step,
    TestimonialContent,
    Typography,
    Value,
    ValuesContent,
)


# --- RGPD gate -------------------------------------------------------------

@pytest.mark.parametrize("email,expected", [
    ("contact@influence-patrimoine.fr",     True),
    ("info@cabinet-bernard.fr",             True),
    ("antoine@maison-laurent.com",          True),
    ("paul.dupont@gmail.com",                False),
    ("user@yahoo.fr",                        False),
    ("client@orange.fr",                     False),
    ("someone@hotmail.fr",                   False),
    ("perso@free.fr",                        False),
    ("user@icloud.com",                      False),
    ("malformed",                            False),
    ("",                                     False),
    ("no-at-sign.com",                       False),
])
def test_is_business_email_filters_personal_domains(email, expected):
    assert is_business_email(email) is expected


def test_personal_domains_includes_french_isps():
    """We must catch the French personal-mail providers — common in real CSVs."""
    for domain in ["orange.fr", "free.fr", "wanadoo.fr", "sfr.fr", "laposte.net"]:
        assert domain in PERSONAL_EMAIL_DOMAINS


# --- First-name extraction -------------------------------------------------

@pytest.mark.parametrize("email,expected", [
    ("jean.dupont@example.fr",   "Jean"),
    ("marie-claire@example.fr",  "Marie"),
    ("contact@example.fr",       ""),       # generic mailbox — skip
    ("info@example.fr",          ""),
    ("noreply@example.fr",       ""),
    ("paul123@example.fr",       ""),       # has digits — not a name
    ("",                          ""),
    ("a@b.c",                     ""),       # too short to extract
])
def test_extract_first_name(email, expected):
    assert extract_first_name(email) == expected


# --- Pydantic enforcement of {{unsubscribe_link}} -------------------------

def test_coldemail_rejects_body_without_unsubscribe():
    """RGPD compliance: every body_html MUST contain the opt-out placeholder."""
    body_long_no_unsub = (
        "<p>Bonjour,</p><p>" + ("x" * 80) + "</p>"
        "<p>Cordialement,</p><p>Alex</p>"
    )
    assert len(body_long_no_unsub) > 120  # passes min_length
    with pytest.raises(ValidationError, match="unsubscribe"):
        ColdEmail(
            subject="petite question",
            preheader="x" * 30,
            body_text="x" * 100,
            body_html=body_long_no_unsub,
            rationale="x" * 30,
        )


def test_coldemail_accepts_unsubscribe_placeholder():
    body_with_unsub = (
        "<p>Bonjour,</p><p>" + ("x" * 60) + "</p>"
        "<small>SIREN — adresse — {{unsubscribe_link}}</small>"
    )
    assert len(body_with_unsub) > 120
    email = ColdEmail(
        subject="petite question",
        preheader="x" * 30,
        body_text="x" * 100,
        body_html=body_with_unsub,
        rationale="x" * 30,
    )
    assert "{{unsubscribe_link}}" in email.body_html


def test_coldemail_subject_max_52_chars():
    """Subject line is hard-capped at 52 chars (mobile Gmail truncation)."""
    with pytest.raises(ValidationError):
        ColdEmail(
            subject="x" * 60,
            preheader="x" * 30,
            body_text="x" * 100,
            body_html="<p>x</p><small>{{unsubscribe_link}}</small>",
            rationale="x" * 30,
        )


# --- SenderIdentity --------------------------------------------------------

def test_sender_identity_requires_siren():
    with pytest.raises(ValidationError):
        SenderIdentity(
            name="Alex", role="Cofondateur", company="X SAS",
            siren="123",  # too short
            address="12 rue X, 75001 Paris",
            reply_to_email="alex@x.fr",
        )


def test_sender_identity_accepts_siren_or_siret():
    """9-digit SIREN or 14-digit SIRET both valid."""
    s = SenderIdentity(
        name="Alex", role="Cofondateur", company="X SAS",
        siren="123456789",
        address="12 rue X, 75001 Paris",
        reply_to_email="alex@x.fr",
    )
    assert s.siren == "123456789"


# --- EmailAgent retry loop -------------------------------------------------

def _valid_email_json():
    return json.dumps({
        "subject": "petite question pour vous",
        "preheader": "Une démo de site moderne pour votre entreprise, à voir.",
        "body_text": "Bonjour,\n\nJ'ai vu votre site et il y a un détail. " * 3,
        "body_html": (
            "<p>Bonjour,</p><p>J'ai vu votre site, il y a un détail.</p>"
            "<p><a href='https://demo.example.fr/'>Voir la démo</a></p>"
            "<p>Alex Dubois<br>Cofondateur · X SAS</p>"
            "<small>Alex Dubois — X SAS — SIREN 123456789<br>"
            "12 rue X, 75001 Paris<br>{{unsubscribe_link}}</small>"
        ),
        "rationale": "Ton refined adapté à un cabinet patrimonial. Hook spécifique sur l'offre.",
    })


def _make_minimal_brand():
    return BrandDNA(
        palette=Palette(bg="#F4EFE5", surface="#EAE3D2", text="#1B1B1F",
                        primary="#14213D", secondary="#B89968"),
        typography=Typography(display_font="Fraunces", body_font="Inter"),
        mood="refined", layout_variant="editorial_classic",
        rationale="x" * 30,
    )


def _make_minimal_content_with_brand(slug, email, brand):
    return SiteContent(
        slug=slug, sector="default",
        meta_description="x" * 100,
        branding=Branding(name="Test SARL", subtitle="Sub", letter="t",
                          phone="0102030405", phone_tel="+33102030405",
                          email=email),
        hero=HeroContent(
            eyebrow="x", h1_line1="A", h1_line2="B", h1_line3_emphasis="CC",
            subtitle="x" * 100, cta_primary="Y", cta_secondary="Z",
            metrics=[HeroMetric(value="1", label="x"),
                     HeroMetric(value="2", label="y"),
                     HeroMetric(value="3", label="z")],
        ),
        manifesto=ManifestoContent(
            eyebrow="x", quote_before="ab", quote_emphasis="mn", quote_after="cd",
            body="x" * 130, founder_name="Alice", founder_role="B",
        ),
        values=ValuesContent(
            eyebrow="x", h2_main="A", h2_emphasis="B", intro="x" * 100,
            entries=[Value(title=f"V{i}", body="x" * 100) for i in range(3)],
        ),
        services=ServicesContent(
            eyebrow="x", h2_main="A", h2_emphasis="B", intro="x" * 100,
            main_service=Service(num="01", title="A", description="x" * 100, is_main=True),
            other_services=[Service(num=str(i), title=f"S{i}", description="x" * 100)
                            for i in range(2, 6)],
        ),
        approach=ApproachContent(
            eyebrow="x", h2_main="A", h2_emphasis="B",
            body_p1="x" * 100, body_p2="x" * 100,
            steps=[Step(num=str(i), title=f"T{i}", body="x" * 100) for i in range(1, 4)],
        ),
        testimonial=TestimonialContent(
            eyebrow="x", quote="x" * 100, name="A", initials="AB", role="x",
        ),
        contact=ContactContent(
            eyebrow="x", h2_main="A", h2_emphasis="B", lead="x" * 100,
            hours="x", office="x", form_title="x", form_subtitle="x",
        ),
        footer_description="x" * 100,
        brand=brand,
    )


def test_email_agent_retries_on_invalid_json():
    fake_llm = MagicMock()
    fake_llm.complete_json.side_effect = ["not json at all", _valid_email_json()]

    agent = EmailAgent(llm=fake_llm)
    sender = SenderIdentity(
        name="Alex Dubois", role="Cofondateur", company="X SAS",
        siren="903456789", address="12 rue X, 75001 Paris",
        reply_to_email="alex@x.fr",
    )

    brand = _make_minimal_brand()
    content = _make_minimal_content_with_brand("test", "contact@test.fr", brand)
    prospect = ProspectInput(slug="test", company_name="Test SARL",
                             email="contact@test.fr")

    result = agent.generate(prospect=prospect, content=content, brand=brand,
                            sender=sender, demo_url="https://demos.x/test/")

    assert result.subject == "petite question pour vous"
    assert "{{unsubscribe_link}}" in result.body_html
    assert fake_llm.complete_json.call_count == 2


def test_email_agent_raises_after_max_retries():
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = "still garbage"

    agent = EmailAgent(llm=fake_llm)
    sender = SenderIdentity(
        name="Alex", role="X", company="Y", siren="123456789",
        address="X", reply_to_email="x@y.z",
    )
    brand = _make_minimal_brand()
    content = _make_minimal_content_with_brand("test", "contact@test.fr", brand)

    with pytest.raises(RuntimeError, match="failed after"):
        agent.generate(
            prospect=ProspectInput(slug="test", company_name="X", email="contact@test.fr"),
            content=content, brand=brand, sender=sender,
            demo_url="https://demos.x/test/",
        )


# --- Instantly client error paths ------------------------------------------

def _mock_response(status_code: int, json_data: dict | None = None,
                   text: str = ""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text or json.dumps(json_data or {})
    return resp


def _fake_client(response):
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.post.return_value = response
    return fake_client


@patch("builder.instantly_client.httpx.Client")
@patch("builder.instantly_client.CONFIG")
def test_instantly_add_lead_success(mock_config, mock_client_class):
    mock_config.instantly_api_key = "fake-key"
    mock_config.instantly_base_url = "https://api.instantly.ai/api/v2"
    mock_client_class.return_value = _fake_client(
        _mock_response(200, {"id": "lead-abc-123"})
    )

    result = add_lead_to_campaign(
        campaign_id="camp-1", email="contact@test.fr",
        company_name="Test SARL", first_name="Alex",
        personalization={"subject": "x", "body_html": "<p>x</p>{{unsubscribe_link}}"},
    )
    assert result.lead_id == "lead-abc-123"


@patch("builder.instantly_client.httpx.Client")
@patch("builder.instantly_client.CONFIG")
def test_instantly_add_lead_auth_error(mock_config, mock_client_class):
    mock_config.instantly_api_key = "fake-key"
    mock_config.instantly_base_url = "https://api.instantly.ai/api/v2"
    mock_client_class.return_value = _fake_client(
        _mock_response(401, text="invalid token")
    )
    with pytest.raises(InstantlyError, match="auth failed"):
        add_lead_to_campaign(
            campaign_id="camp-1", email="contact@test.fr", company_name="Test",
        )


@patch("builder.instantly_client.httpx.Client")
@patch("builder.instantly_client.CONFIG")
def test_instantly_add_lead_campaign_not_found(mock_config, mock_client_class):
    mock_config.instantly_api_key = "fake-key"
    mock_config.instantly_base_url = "https://api.instantly.ai/api/v2"
    mock_client_class.return_value = _fake_client(_mock_response(404, text="not found"))
    with pytest.raises(InstantlyError, match="Campaign not found"):
        add_lead_to_campaign(
            campaign_id="bad-id", email="contact@test.fr", company_name="Test",
        )


@patch("builder.instantly_client.httpx.Client")
@patch("builder.instantly_client.CONFIG")
def test_instantly_add_lead_duplicate_409(mock_config, mock_client_class):
    mock_config.instantly_api_key = "fake-key"
    mock_config.instantly_base_url = "https://api.instantly.ai/api/v2"
    mock_client_class.return_value = _fake_client(_mock_response(409, text="duplicate"))
    with pytest.raises(InstantlyError, match="already exists"):
        add_lead_to_campaign(
            campaign_id="camp-1", email="contact@test.fr", company_name="Test",
        )


def test_instantly_preflight_reports_all_missing(monkeypatch):
    """preflight() surfaces all missing config in one go."""
    monkeypatch.setenv("INSTANTLY_API_KEY", "")
    monkeypatch.setenv("INSTANTLY_CAMPAIGN_ID", "")
    monkeypatch.setenv("SENDER_NAME", "")
    monkeypatch.setenv("SENDER_COMPANY", "")
    monkeypatch.setenv("SENDER_SIREN", "")
    monkeypatch.setenv("SENDER_ADDRESS", "")
    monkeypatch.setenv("SENDER_REPLY_TO", "")
    from importlib import reload
    import builder.config as cfg
    reload(cfg)
    import builder.instantly_client as ic
    reload(ic)

    issues = ic.preflight()
    text = " | ".join(issues)
    assert "INSTANTLY_API_KEY" in text
    assert "INSTANTLY_CAMPAIGN_ID" in text
    assert "SIREN" in text
    assert "ADDRESS" in text
    assert "REPLY_TO" in text


# --- DB transitions --------------------------------------------------------

def test_list_deployed_unsent_filters_correctly(tmp_path):
    repo = BuildsRepo(db_path=tmp_path / "test.db")
    repo.upsert_pending("a", "A SARL")
    repo.upsert_pending("b", "B SARL")
    repo.upsert_pending("c", "C SARL")
    repo.upsert_pending("d", "D SARL")  # deployed but already emailed
    repo.upsert_pending("e", "E SARL")  # deployed but in error state

    with repo._conn() as conn:
        # a: not deployed
        conn.execute("UPDATE builds SET status='rendered' WHERE slug='a'")
        # b: deployed, never emailed → should appear
        conn.execute("UPDATE builds SET status='qa_passed', deployed_url='https://x/b' "
                     "WHERE slug='b'")
        # c: deployed, never emailed → should appear
        conn.execute("UPDATE builds SET status='qa_passed', deployed_url='https://x/c' "
                     "WHERE slug='c'")
        # d: deployed AND already emailed → should NOT appear
        conn.execute(
            "UPDATE builds SET status='qa_passed', deployed_url='https://x/d', "
            "email_sent_at='2025-01-01 00:00:00' WHERE slug='d'"
        )
        # e: deployed AND in error → should NOT appear (sticky failure)
        conn.execute(
            "UPDATE builds SET status='qa_passed', deployed_url='https://x/e', "
            "email_error='auth fail' WHERE slug='e'"
        )

    slugs = {r.slug for r in repo.list_deployed_unsent()}
    assert slugs == {"b", "c"}


def test_record_email_sent_persists_full_record(tmp_path):
    repo = BuildsRepo(db_path=tmp_path / "test.db")
    repo.upsert_pending("foo", "Foo SARL")
    with repo._conn() as conn:
        conn.execute(
            "UPDATE builds SET deployed_url='https://x/foo' WHERE slug='foo'"
        )

    repo.record_email_sent(
        slug="foo", target="contact@foo.fr",
        subject="petite question", body_html="<p>x</p>",
        provider="instantly", lead_id="lead-1",
    )
    row = repo.get("foo")
    assert row.email_target == "contact@foo.fr"
    assert row.email_subject == "petite question"
    assert row.email_body_html == "<p>x</p>"
    assert row.email_provider == "instantly"
    assert row.email_lead_id == "lead-1"
    assert row.email_sent_at is not None
    assert row.email_error is None


def test_record_email_failure_sets_error(tmp_path):
    repo = BuildsRepo(db_path=tmp_path / "test.db")
    repo.upsert_pending("bar", "Bar SARL")
    repo.record_email_failure("bar", "instantly: 401 invalid token")
    row = repo.get("bar")
    assert row.email_error == "instantly: 401 invalid token"
    assert row.email_sent_at is None


# --- send_one end-to-end ---------------------------------------------------

def test_send_one_refuses_personal_email(tmp_path):
    """The RGPD gate must short-circuit even before calling the LLM."""
    repo = BuildsRepo(db_path=tmp_path / "test.db")
    repo.upsert_pending("foo", "Foo SARL")
    brand = _make_minimal_brand()
    content = _make_minimal_content_with_brand("foo", "paul.dupont@gmail.com", brand)
    with repo._conn() as conn:
        conn.execute(
            "UPDATE builds SET deployed_url=?, content_json=? WHERE slug='foo'",
            ("https://x/foo", content.model_dump_json()),
        )

    fake_agent = MagicMock()
    fake_sender = SenderIdentity(
        name="Alex", role="X", company="Y", siren="123456789",
        address="12 rue X, 75001 Paris", reply_to_email="alex@y.fr",
    )

    row = repo.get("foo")
    result = send_one(row, agent=fake_agent, sender=fake_sender, repo=repo, dry_run=False)

    assert result.ok is False
    assert result.skipped == "personal_email"
    fake_agent.generate.assert_not_called()  # short-circuited before LLM
    # And the failure is recorded so we don't retry forever
    assert repo.get("foo").email_error is not None


def test_send_one_dry_run_does_not_call_instantly(tmp_path):
    repo = BuildsRepo(db_path=tmp_path / "test.db")
    repo.upsert_pending("baz", "Baz SARL")
    brand = _make_minimal_brand()
    content = _make_minimal_content_with_brand("baz", "contact@baz.fr", brand)
    with repo._conn() as conn:
        conn.execute(
            "UPDATE builds SET deployed_url=?, content_json=? WHERE slug='baz'",
            ("https://x/baz", content.model_dump_json()),
        )

    fake_agent = MagicMock()
    fake_agent.generate.return_value = ColdEmail(
        subject="petite question pour vous",
        preheader="x" * 30,
        body_text="x" * 100,
        body_html=("<p>Bonjour,</p><p>" + ("x" * 60) + "</p>"
                   "<small>SIREN — adresse — {{unsubscribe_link}}</small>"),
        rationale="x" * 30,
    )
    fake_sender = SenderIdentity(
        name="Alex", role="X", company="Y", siren="123456789",
        address="12 rue X, 75001 Paris", reply_to_email="alex@y.fr",
    )

    with patch("builder.email_sender.add_lead_to_campaign") as fake_instantly:
        result = send_one(repo.get("baz"), agent=fake_agent, sender=fake_sender,
                          repo=repo, dry_run=True)
        fake_instantly.assert_not_called()

    assert result.ok is True
    assert result.lead_id == "dry-run"
    # In dry-run we don't mark as sent
    assert repo.get("baz").email_sent_at is None
