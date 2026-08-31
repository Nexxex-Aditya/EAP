"""Abstract browser adapter interface.

Per architecture.md §8 and §12, all browser interactions go through this
interface. Playwright handles deterministic operations; Browser Use handles
semantic recovery — both implement this same ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BrowserAdapter(ABC):
    """Abstract interface for browser automation."""

    @abstractmethod
    async def open_session(self, *, headless: bool = True) -> None:
        """Start a new browser session."""

    @abstractmethod
    async def navigate(self, url: str) -> None:
        """Navigate to the given URL."""

    @abstractmethod
    async def inspect(self, selector: str = "") -> dict[str, Any]:
        """Inspect the current page state, optionally scoped to a selector."""

    @abstractmethod
    async def click(self, selector: str) -> None:
        """Click an element identified by selector."""

    @abstractmethod
    async def type_text(self, selector: str, text: str) -> None:
        """Type text into an input element."""

    @abstractmethod
    async def select(self, selector: str, value: str) -> None:
        """Select a value from a dropdown/select element."""

    @abstractmethod
    async def extract(self, selector: str) -> str:
        """Extract text content from an element."""

    @abstractmethod
    async def extract_all(self, selector: str) -> list[str]:
        """Extract text content from all matching elements."""

    @abstractmethod
    async def wait_for(self, selector: str, *, timeout_ms: int = 30000) -> bool:
        """Wait for an element to appear. Returns True if found within timeout."""

    @abstractmethod
    async def screenshot(self, path: str) -> str:
        """Capture a screenshot and save to path. Returns the file path."""

    @abstractmethod
    async def get_page_title(self) -> str:
        """Return the current page title."""

    @abstractmethod
    async def get_page_url(self) -> str:
        """Return the current page URL."""

    @abstractmethod
    async def is_element_visible(self, selector: str) -> bool:
        """Check if an element is visible on the page."""

    @abstractmethod
    async def close(self) -> None:
        """Close the browser session."""
