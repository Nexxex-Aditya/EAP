"""Playwright browser adapter — deterministic browser automation.

Per architecture.md §12 and rules.md §8, deterministic browser interactions
use Playwright. Semantic recovery uses Browser Use (Phase 6).
Both implement the same BrowserAdapter interface.
"""

from __future__ import annotations

from typing import Any

from eap.adapters.browser.interface import BrowserAdapter
from eap.core.config import get_logger

logger = get_logger("adapters.browser.playwright")


class PlaywrightBrowserAdapter(BrowserAdapter):
    """Browser adapter using Playwright for deterministic operations."""

    def __init__(self, *, browser_type: str = "chromium") -> None:
        self._browser_type = browser_type
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    async def open_session(self, *, headless: bool = True) -> None:
        """Start a new Playwright browser session."""
        from playwright.async_api import async_playwright  # type: ignore

        self._pw = await async_playwright().start()

        launcher = getattr(self._pw, self._browser_type)
        self._browser = await launcher.launch(headless=headless)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

        logger.info(
            "playwright_session_started",
            browser=self._browser_type,
            headless=headless,
        )

    async def navigate(self, url: str) -> None:
        """Navigate to a URL."""
        page = self._require_page()
        await page.goto(url, wait_until="networkidle")
        logger.info("navigated", url=url)

    async def inspect(self, selector: str = "") -> dict[str, Any]:
        """Inspect page state."""
        page = self._require_page()
        result: dict[str, Any] = {
            "url": page.url,
            "title": await page.title(),
        }
        if selector:
            elements = await page.query_selector_all(selector)
            result["element_count"] = len(elements)
            if elements:
                result["first_text"] = await elements[0].text_content()
                result["first_visible"] = await elements[0].is_visible()
        return result

    async def click(self, selector: str) -> None:
        """Click an element."""
        page = self._require_page()
        await page.click(selector)
        logger.info("clicked", selector=selector)

    async def type_text(self, selector: str, text: str) -> None:
        """Type text into an input."""
        page = self._require_page()
        await page.fill(selector, text)
        logger.info("typed", selector=selector, length=len(text))

    async def select(self, selector: str, value: str) -> None:
        """Select a dropdown value."""
        page = self._require_page()
        await page.select_option(selector, value=value)
        logger.info("selected", selector=selector, value=value)

    async def extract(self, selector: str) -> str:
        """Extract text from an element."""
        page = self._require_page()
        el = await page.query_selector(selector)
        if el:
            return await el.text_content() or ""
        return ""

    async def extract_all(self, selector: str) -> list[str]:
        """Extract text from all matching elements."""
        page = self._require_page()
        elements = await page.query_selector_all(selector)
        results: list[str] = []
        for el in elements:
            text = await el.text_content()
            results.append(text or "")
        return results

    async def wait_for(self, selector: str, *, timeout_ms: int = 30000) -> bool:
        """Wait for an element to appear."""
        page = self._require_page()
        try:
            await page.wait_for_selector(selector, timeout=timeout_ms)
            return True
        except Exception:
            return False

    async def screenshot(self, path: str) -> str:
        """Capture a screenshot."""
        page = self._require_page()
        await page.screenshot(path=path, full_page=True)
        logger.info("screenshot_captured", path=path)
        return path

    async def get_page_title(self) -> str:
        """Return page title."""
        page = self._require_page()
        return await page.title()

    async def get_page_url(self) -> str:
        """Return page URL."""
        page = self._require_page()
        return page.url

    async def is_element_visible(self, selector: str) -> bool:
        """Check element visibility."""
        page = self._require_page()
        try:
            el = await page.query_selector(selector)
            if el:
                return await el.is_visible()
        except Exception:
            pass
        return False

    async def close(self) -> None:
        """Close the browser session."""
        try:
            if self._browser:
                await self._browser.close()
            if hasattr(self, "_pw") and self._pw:
                await self._pw.stop()
            logger.info("playwright_session_closed")
        except Exception as e:
            logger.warning("playwright_close_error", error=str(e))

    def _require_page(self) -> Any:
        """Ensure a page is available."""
        if self._page is None:
            raise RuntimeError("No browser session — call open_session() first")
        return self._page
