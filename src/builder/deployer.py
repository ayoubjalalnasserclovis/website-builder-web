"""Cloudflare Pages deployer.

Architecture: hybrid Wrangler + direct API.
  - Project lookup / creation → Cloudflare REST API (via httpx). Reliable,
    JSON-typed, no fragile stdout parsing.
  - File upload → Wrangler subprocess. The Direct Upload protocol has a 5-step
    JWT flow that is non-trivial to reimplement and changes occasionally; we
    delegate to the official tool.
  - Deployment URL fetch → API first (canonical), wrangler stdout regex as fallback.

Prerequisites on the user's machine:
  - Node.js + Wrangler:    npm install -g wrangler

Auth:
  Set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in .env. The token is
  passed both to the API (Bearer header) and wrangler (env var).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx
from rich.console import Console

from .config import CONFIG
from .db import BuildsRepo

console = Console()

_CF_API_BASE = "https://api.cloudflare.com/client/v4"
_CF_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class DeployError(RuntimeError):
    """Raised when a pre-flight or deploy step fails."""


@dataclass
class DeployResult:
    project_name: str
    deployment_url: str           # Hashed deployment URL, e.g. https://abc123.demos.pages.dev
    public_base_url: str          # Stable base — custom domain or default *.pages.dev
    deployed_slugs: list[str]
    created_project: bool         # True if we just created the Pages project


# --- Subprocess helpers -----------------------------------------------------

def _wrangler_available() -> bool:
    """Wrangler installed (either standalone or via npx)."""
    return shutil.which("wrangler") is not None or shutil.which("npx") is not None


def _wrangler_cmd() -> list[str]:
    """Prefer the standalone wrangler binary. Fall back to npx."""
    if shutil.which("wrangler"):
        return ["wrangler"]
    return ["npx", "--yes", "wrangler@latest"]


def _build_env() -> dict[str, str]:
    """Pass CF auth via env so wrangler picks it up."""
    env = os.environ.copy()
    if CONFIG.cf_api_token:
        env["CLOUDFLARE_API_TOKEN"] = CONFIG.cf_api_token
    if CONFIG.cf_account_id:
        env["CLOUDFLARE_ACCOUNT_ID"] = CONFIG.cf_account_id
    # Disable wrangler telemetry banners for cleaner output
    env["WRANGLER_SEND_METRICS"] = "false"
    return env


def _run_wrangler(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    cmd = _wrangler_cmd() + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=_build_env(),
        timeout=timeout,
        check=False,
        stdin=subprocess.DEVNULL,  # never wait for interactive input
    )


# --- Pre-flight --------------------------------------------------------------

def preflight() -> list[str]:
    """Return list of issues. Empty list = ready to deploy."""
    issues: list[str] = []
    if not _wrangler_available():
        issues.append(
            "Wrangler not found. Install it: `npm install -g wrangler` "
            "(requires Node.js)."
        )
    if not CONFIG.cf_api_token:
        issues.append("CLOUDFLARE_API_TOKEN missing in .env")
    if not CONFIG.cf_account_id:
        issues.append("CLOUDFLARE_ACCOUNT_ID missing in .env")
    if not CONFIG.cf_pages_project:
        issues.append("CLOUDFLARE_PAGES_PROJECT missing in .env "
                      "(pick any name, e.g. 'demos')")
    if not CONFIG.output_dir.exists():
        issues.append(f"Output dir does not exist: {CONFIG.output_dir}. "
                      "Run `python scripts/build_all.py` first.")
    elif not _list_slugs(CONFIG.output_dir):
        issues.append(f"No built sites in {CONFIG.output_dir} "
                      "(expected <slug>/index.html in subdirs).")
    return issues


# --- Cloudflare REST API (direct, no wrangler stdout parsing) ---------------

def _cf_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {CONFIG.cf_api_token}",
        "Content-Type": "application/json",
    }


def _project_exists(project_name: str) -> bool:
    """Direct API call. Returns True/False; raises only on non-200/404."""
    url = (f"{_CF_API_BASE}/accounts/{CONFIG.cf_account_id}"
           f"/pages/projects/{project_name}")
    try:
        with httpx.Client(timeout=_CF_HTTP_TIMEOUT) as c:
            r = c.get(url, headers=_cf_headers())
    except httpx.HTTPError as e:
        raise DeployError(f"Cloudflare API unreachable: {e}") from e

    if r.status_code == 200:
        return True
    if r.status_code == 404:
        return False
    if r.status_code in (401, 403):
        raise DeployError(
            f"Cloudflare API auth failed ({r.status_code}). "
            f"Check CLOUDFLARE_API_TOKEN scope (needs Pages:Edit) and "
            f"CLOUDFLARE_ACCOUNT_ID."
        )
    raise DeployError(
        f"Unexpected response from Cloudflare API ({r.status_code}): {r.text[:300]}"
    )


def _create_project(project_name: str) -> None:
    """Direct API call. Creates a Pages project with default Direct Upload settings."""
    url = f"{_CF_API_BASE}/accounts/{CONFIG.cf_account_id}/pages/projects"
    payload = {
        "name": project_name,
        "production_branch": "main",
    }
    try:
        with httpx.Client(timeout=_CF_HTTP_TIMEOUT) as c:
            r = c.post(url, headers=_cf_headers(), json=payload)
    except httpx.HTTPError as e:
        raise DeployError(f"Cloudflare API unreachable while creating project: {e}") from e

    if r.status_code in (200, 201):
        return
    raise DeployError(
        f"Failed to create Pages project '{project_name}' "
        f"({r.status_code}): {r.text[:400]}"
    )


def _fetch_latest_deployment(project_name: str) -> dict | None:
    """Pull the most recent deployment record for canonical URL/ID."""
    url = (f"{_CF_API_BASE}/accounts/{CONFIG.cf_account_id}"
           f"/pages/projects/{project_name}/deployments?per_page=1")
    try:
        with httpx.Client(timeout=_CF_HTTP_TIMEOUT) as c:
            r = c.get(url, headers=_cf_headers())
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    deployments = data.get("result") or []
    return deployments[0] if deployments else None


# --- Deploy ------------------------------------------------------------------

_DEPLOY_URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.[\w-]+\.pages\.dev")


def _parse_deployment_url(stdout: str) -> str:
    """Wrangler prints the deployment URL near the end. Take the last match."""
    matches = _DEPLOY_URL_RE.findall(stdout)
    return matches[-1] if matches else ""


def _list_slugs(dist_dir: Path) -> list[str]:
    """Each subdir of dist/ that has index.html is a deployable slug."""
    if not dist_dir.exists():
        return []
    return sorted(
        p.name for p in dist_dir.iterdir()
        if p.is_dir() and (p / "index.html").exists()
    )


def _build_deploy_dir(dist_dir: Path, allowed_slugs: set[str]) -> Path:
    """Materialize a temp dir containing only the slugs we want to publish.

    We can't ask Wrangler to publish a subset of dist/ — it always publishes
    the whole directory. So we mirror only the allowed slugs into a temp dir
    and point Wrangler at that.

    Uses os.symlink for speed (no file copy), with a fallback to copy on
    platforms that disallow it (Windows without dev mode).
    """
    tmp = Path(tempfile.mkdtemp(prefix="website-builder-deploy-"))
    for slug in allowed_slugs:
        src = dist_dir / slug
        if not src.is_dir():
            continue
        target = tmp / slug
        try:
            os.symlink(src.resolve(), target, target_is_directory=True)
        except (OSError, NotImplementedError):
            shutil.copytree(src, target)
    return tmp


def deploy(
    dist_dir: Path | None = None,
    project_name: str | None = None,
    public_base_url: str | None = None,
    qa_strict: bool = True,
) -> DeployResult:
    """Deploy the dist/ directory to Cloudflare Pages.

    All slugs are exposed at  {public_base_url}/<slug>/  (or the default
    *.pages.dev URL if no custom domain is configured).

    qa_strict (default True): only publish slugs whose DB status is in
        ('rendered', 'qa_passed'). Slugs in 'qa_rejected' or 'failed' are
        silently filtered out. Set False to publish whatever is in dist/.
    """
    dist_dir = dist_dir or CONFIG.output_dir
    project_name = project_name or CONFIG.cf_pages_project
    public_base_url = (public_base_url or CONFIG.public_base_url or "").rstrip("/")

    issues = preflight()
    if issues:
        raise DeployError("Pre-flight failed:\n  - " + "\n  - ".join(issues))

    fs_slugs = set(_list_slugs(dist_dir))

    # Filter against DB if qa_strict
    deploy_dir = dist_dir
    cleanup: Path | None = None
    if qa_strict:
        repo = BuildsRepo()
        deployable = {b.slug for b in repo.list_deployable()}
        publishable = fs_slugs & deployable
        rejected_count = len(fs_slugs - deployable)
        if rejected_count > 0:
            console.print(
                f"[yellow]Filtering out {rejected_count} slug(s) "
                f"(qa_rejected or not in DB)[/]"
            )
        if not publishable:
            raise DeployError(
                "No deployable sites after QA filter. "
                "Run `python scripts/qa.py` to QA your rendered sites first, "
                "or pass qa_strict=False to bypass."
            )
        deploy_dir = _build_deploy_dir(dist_dir, publishable)
        cleanup = deploy_dir
        slugs = sorted(publishable)
    else:
        slugs = sorted(fs_slugs)

    console.print(f"[bold]Deploying[/] {len(slugs)} sites → "
                  f"project [cyan]{project_name}[/]")

    # Ensure the project exists
    created = False
    if not _project_exists(project_name):
        console.print(f"[yellow]Project '{project_name}' not found. Creating...[/]")
        _create_project(project_name)
        created = True
        console.print(f"[green]✓ Created Pages project '{project_name}'[/]")

    # Run the actual deploy (the only step we delegate to wrangler)
    try:
        result = _run_wrangler(
            ["pages", "deploy", str(deploy_dir),
             "--project-name", project_name,
             "--commit-dirty=true",
             "--branch=main"],
            timeout=600,
        )
    finally:
        # Clean up the temp dir whether wrangler succeeded or failed
        if cleanup is not None:
            shutil.rmtree(cleanup, ignore_errors=True)
    if result.returncode != 0:
        raise DeployError(
            f"Wrangler deploy failed (exit {result.returncode}):\n"
            f"--- stdout ---\n{result.stdout.strip()}\n"
            f"--- stderr ---\n{result.stderr.strip()}"
        )

    # Canonical deployment URL: ask the API (more reliable than parsing stdout).
    # If the API is unreachable for some reason, fall back to regex on stdout.
    deployment_url = ""
    latest = _fetch_latest_deployment(project_name)
    if latest:
        deployment_url = latest.get("url") or ""
    if not deployment_url:
        deployment_url = _parse_deployment_url(result.stdout)

    # Determine the public base for stable URLs.
    # Priority: explicit custom domain > default <project>.pages.dev
    if public_base_url:
        base = public_base_url
    elif deployment_url:
        # Strip the hashed prefix to get the canonical project URL
        # e.g. https://abc123.demos.pages.dev → https://demos.pages.dev
        m = re.match(r"https://[^.]+\.([\w-]+\.pages\.dev)", deployment_url)
        base = f"https://{m.group(1)}" if m else deployment_url
    else:
        base = f"https://{project_name}.pages.dev"

    # Update the DB: set deployed_url for each slug we just published
    repo = BuildsRepo()
    for slug in slugs:
        url = f"{base}/{slug}/"
        repo.set_deployed_url(slug, url)

    console.print(f"\n[green]✓ Deployment complete.[/]")
    if deployment_url:
        console.print(f"  Deployment:   {deployment_url}")
    console.print(f"  Public base:  {base}")

    return DeployResult(
        project_name=project_name,
        deployment_url=deployment_url,
        public_base_url=base,
        deployed_slugs=slugs,
        created_project=created,
    )
