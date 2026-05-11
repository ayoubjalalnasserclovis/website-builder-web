"""Tests for deployer module.

Covers the pure functions (URL parsing, slug listing, preflight error messages)
and the API-based project lookup with mocked httpx responses. The actual
wrangler deploy is covered by integration tests against a real CF account
(not run here — requires credentials).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from builder.deployer import (
    DeployError,
    _fetch_latest_deployment,
    _list_slugs,
    _parse_deployment_url,
    _project_exists,
    preflight,
)


def test_parse_deployment_url_extracts_pages_dev():
    output = """\
✨ Compiled Worker successfully
🌎  Deploying to Cloudflare Pages

Uploading... (3/3) ✨
🌎  Deployment complete! Take a peek over at https://abc123.demos.pages.dev
"""
    assert _parse_deployment_url(output) == "https://abc123.demos.pages.dev"


def test_parse_deployment_url_handles_missing():
    assert _parse_deployment_url("nothing here") == ""


def test_parse_deployment_url_takes_last_match():
    """If multiple URLs appear, take the last one (the actual deployment URL)."""
    output = "Visit https://old123.demos.pages.dev for old version. " \
             "New version at https://new456.demos.pages.dev now live."
    assert _parse_deployment_url(output) == "https://new456.demos.pages.dev"


def test_list_slugs_finds_index_html_subdirs(tmp_path):
    (tmp_path / "abc" / "index.html").parent.mkdir(parents=True)
    (tmp_path / "abc" / "index.html").write_text("<html></html>")
    (tmp_path / "xyz" / "index.html").parent.mkdir(parents=True)
    (tmp_path / "xyz" / "index.html").write_text("<html></html>")
    (tmp_path / "incomplete").mkdir()  # no index.html — should be ignored
    (tmp_path / "loose-file.txt").write_text("not a site")  # should be ignored

    slugs = _list_slugs(tmp_path)
    assert slugs == ["abc", "xyz"]


def test_list_slugs_handles_missing_dir(tmp_path):
    """Non-existent dir returns empty list, not an error."""
    assert _list_slugs(tmp_path / "does-not-exist") == []


def _mock_httpx_response(status_code: int, json_data: dict | None = None,
                          text: str = ""):
    """Build a fake httpx.Response for the patched client."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text or (json_data and str(json_data)) or ""
    return resp


def _make_fake_client(response):
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = response
    fake_client.post.return_value = response
    return fake_client


@patch("builder.deployer.httpx.Client")
def test_project_exists_returns_true_on_200(mock_client_class):
    mock_client_class.return_value = _make_fake_client(
        _mock_httpx_response(200, {"result": {}})
    )
    assert _project_exists("demos") is True


@patch("builder.deployer.httpx.Client")
def test_project_exists_returns_false_on_404(mock_client_class):
    mock_client_class.return_value = _make_fake_client(_mock_httpx_response(404))
    assert _project_exists("does-not-exist") is False


@patch("builder.deployer.httpx.Client")
def test_project_exists_raises_on_auth_error(mock_client_class):
    mock_client_class.return_value = _make_fake_client(
        _mock_httpx_response(401, text="invalid token")
    )
    with pytest.raises(DeployError, match="auth failed"):
        _project_exists("demos")


@patch("builder.deployer.httpx.Client")
def test_fetch_latest_deployment_returns_url(mock_client_class):
    mock_client_class.return_value = _make_fake_client(_mock_httpx_response(
        200,
        {"result": [{"id": "abc123", "url": "https://abc123.demos.pages.dev"}]}
    ))
    deployment = _fetch_latest_deployment("demos")
    assert deployment is not None
    assert deployment["url"] == "https://abc123.demos.pages.dev"


@patch("builder.deployer.httpx.Client")
def test_fetch_latest_deployment_returns_none_on_api_error(mock_client_class):
    mock_client_class.return_value = _make_fake_client(_mock_httpx_response(500))
    assert _fetch_latest_deployment("demos") is None


def test_preflight_reports_all_missing_creds(monkeypatch):
    """When everything's missing, preflight surfaces all issues at once."""
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "")
    monkeypatch.setenv("CLOUDFLARE_PAGES_PROJECT", "")
    # Reload Config to pick up the cleared env
    from importlib import reload
    import builder.config as config_module
    reload(config_module)
    import builder.deployer as deployer_module
    reload(deployer_module)

    issues = deployer_module.preflight()
    text = " | ".join(issues)
    assert "CLOUDFLARE_API_TOKEN" in text
    assert "CLOUDFLARE_ACCOUNT_ID" in text
    assert "CLOUDFLARE_PAGES_PROJECT" in text
