"""Playwright screenshot helper.

Why headless Chromium and not just rendering the HTML to PDF: we need an
actual browser to load Google Fonts (Fraunces), apply CSS, and produce a
pixel-true rendering that the vision LLM can grade.

Concurrency: one browser instance, many pages. New page per screenshot,
closed immediately after. Cap concurrent pages at QA_CONCURRENCY (3 by
default) to avoid OOM on small machines.

Output: JPEG quality 75 — keeps the file under ~300KB even for tall pages,
small enough to fit any vision API budget.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from .config import CONFIG


class PlaywrightMissing(RuntimeError):
    """Raised when playwright isn't installed (it's an optional extra)."""


def _ensure_playwright():
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError as e:
        raise PlaywrightMissing(
            "Playwright not installed. Run:\n"
            "  pip install -e .[qa]\n"
            "  playwright install chromium"
        ) from e


@asynccontextmanager
async def shared_browser() -> AsyncIterator["Browser"]:
    """Yield a single Browser instance for the lifetime of a batch.

    Reuse via `async with shared_browser() as browser: ...` then call
    take_screenshot(browser, ...) multiple times.
    """
    _ensure_playwright()
    from playwright.async_api import async_playwright
    from playwright._impl._errors import Error as PlaywrightError

    p = await async_playwright().start()
    try:
        browser = await p.chromium.launch(headless=True)
    except PlaywrightError as e:
        await p.stop()
        msg = str(e)
        if "shared libraries" in msg or "libatk" in msg or "libnss" in msg:
            raise PlaywrightMissing(
                "Chromium launch failed because system libraries are missing. "
                "Run:\n"
                "  sudo playwright install-deps   (Linux only, requires sudo)\n"
                "Or install the deps manually (Debian/Ubuntu):\n"
                "  sudo apt-get install -y libatk1.0-0 libatk-bridge2.0-0 libnss3 "
                "libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libxfixes3 "
                "libgbm1 libxss1 libasound2 libpangocairo-1.0-0 libpango-1.0-0"
            ) from e
        raise
    try:
        yield Browser(browser)
    finally:
        await browser.close()
        await p.stop()


class Browser:
    """Wraps a Playwright browser to expose .screenshot() with sensible defaults."""

    def __init__(self, browser):
        self._browser = browser
        # Concurrency limiter: serializes new_page calls beyond QA_CONCURRENCY.
        self._sem = asyncio.Semaphore(CONFIG.qa_concurrency)

    async def screenshot(self, html_path: Path, out_path: Path,
                         viewport: tuple[int, int] | None = None,
                         full_page: bool = True,
                         quality: int = 75,
                         wait_ms: int = 800) -> Path:
        """Render html_path in headless Chromium and write a JPEG to out_path."""
        viewport = viewport or (CONFIG.qa_viewport_width, CONFIG.qa_viewport_height)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        async with self._sem:
            context = await self._browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                device_scale_factor=1,
            )
            page = await context.new_page()
            try:
                # file:// URL needs absolute path
                await page.goto(f"file://{html_path.resolve()}", wait_until="networkidle")
                # Extra settle for fonts (Google Fonts FOUC) + animations
                await page.wait_for_timeout(wait_ms)
                await page.screenshot(
                    path=str(out_path),
                    full_page=full_page,
                    type="jpeg",
                    quality=quality,
                )
            finally:
                await page.close()
                await context.close()

        return out_path
