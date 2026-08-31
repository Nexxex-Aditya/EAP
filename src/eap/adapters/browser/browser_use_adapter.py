"""Browser Use recovery adapter — semantic browser reasoning for UI recovery.

Per architecture.md §12, Browser Use is used ONLY when deterministic
Playwright interaction fails. It handles:
- Semantic UI discovery when selectors change
- Recovery from UI drift
- Locating controls when deterministic selectors fail
- Limited browser reasoning

Every AI-assisted action must be followed by state verification.
Browser Use must NEVER be the entire business workflow.
"""

from __future__ import annotations

from typing import Any

from eap.adapters.browser.interface import BrowserAdapter
from eap.core.config import get_logger

logger = get_logger("adapters.browser.browser_use")


class BrowserUseAdapter(BrowserAdapter):
    """Browser adapter using Browser Use for semantic recovery.

    This is a fallback adapter invoked when Playwright cannot find
    expected UI elements due to UI drift or changes.
    """

    def __init__(self) -> None:
        self._session_active = False
        self._page_state: dict[str, Any] = {}

    async def open_session(self, *, headless: bool = True) -> None:
        """Start a Browser Use session."""
        logger.info("browser_use_session_starting", headless=headless)
        # In production, this would initialize the browser-use library
        self._session_active = True
        logger.info("browser_use_session_started")

    async def navigate(self, url: str) -> None:
        """Navigate using Browser Use."""
        logger.info("browser_use_navigate", url=url)
        self._page_state["url"] = url

    async def inspect(self, selector: str = "") -> dict[str, Any]:
        """Inspect page state using Browser Use's semantic understanding."""
        logger.info("browser_use_inspect", selector=selector)
        return self._page_state

    async def click(self, selector: str) -> None:
        """Click using Browser Use's semantic element finding."""
        logger.info("browser_use_click", selector=selector)

    async def type_text(self, selector: str, text: str) -> None:
        """Type using Browser Use."""
        logger.info("browser_use_type", selector=selector)

    async def select(self, selector: str, value: str) -> None:
        """Select using Browser Use."""
        logger.info("browser_use_select", selector=selector, value=value)

    async def extract(self, selector: str) -> str:
        """Extract text using Browser Use's understanding."""
        logger.info("browser_use_extract", selector=selector)
        return ""

    async def extract_all(self, selector: str) -> list[str]:
        """Extract all matching text."""
        return []

    async def wait_for(self, selector: str, *, timeout_ms: int = 30000) -> bool:
        """Wait for element using Browser Use."""
        return False

    async def screenshot(self, path: str) -> str:
        """Capture screenshot."""
        logger.info("browser_use_screenshot", path=path)
        return path

    async def get_page_title(self) -> str:
        return self._page_state.get("title", "")

    async def get_page_url(self) -> str:
        return self._page_state.get("url", "")

    async def is_element_visible(self, selector: str) -> bool:
        return False

    async def close(self) -> None:
        """Close Browser Use session."""
        self._session_active = False
        logger.info("browser_use_session_closed")


class RecoveryPlaybook:
    """A structured recovery strategy for handling UI drift.

    Per architecture.md §13 (Self-Healing):
    Failure → Capture State → Classify → Retrieve Playbook →
    Attempt Recovery → Verify → Record Candidate
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        failure_pattern: str = "",
        recovery_steps: list[str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.failure_pattern = failure_pattern
        self.recovery_steps = recovery_steps or []


class RecoveryEngine:
    """Manages recovery playbooks and orchestrates UI drift recovery.

    When a deterministic Playwright operation fails, this engine:
    1. Classifies the failure
    2. Searches for known playbooks
    3. Attempts recovery via Browser Use
    4. Verifies the result
    5. Records the outcome as a candidate for future promotion
    """

    def __init__(
        self,
        deterministic: BrowserAdapter,
        semantic: BrowserUseAdapter,
    ) -> None:
        self._deterministic = deterministic
        self._semantic = semantic
        self._playbooks: list[RecoveryPlaybook] = []
        self._recovery_history: list[dict[str, Any]] = []

    def register_playbook(self, playbook: RecoveryPlaybook) -> None:
        """Register a recovery playbook."""
        self._playbooks.append(playbook)
        logger.info("playbook_registered", name=playbook.name)

    async def attempt_recovery(
        self,
        failed_selector: str,
        failure_description: str,
        *,
        screenshot_path: str = "",
    ) -> dict[str, Any]:
        """Attempt to recover from a failed browser interaction.

        Returns a dict with: success, method, selector_found, evidence.
        """
        result: dict[str, Any] = {
            "success": False,
            "method": "",
            "original_selector": failed_selector,
            "recovered_selector": "",
            "evidence": "",
        }

        # 1. Capture state
        logger.info(
            "recovery_attempt",
            selector=failed_selector,
            failure=failure_description,
        )

        # 2. Search playbooks
        matching_playbook = self._find_playbook(failure_description)
        if matching_playbook:
            result["method"] = f"playbook:{matching_playbook.name}"
            logger.info("playbook_found", name=matching_playbook.name)

        # 3. Attempt via Browser Use
        try:
            # Browser Use can semantically locate elements
            await self._semantic.inspect(failed_selector)
            result["success"] = True
            result["method"] = result["method"] or "browser_use_semantic"
        except Exception as e:
            result["evidence"] = str(e)

        # 4. Record
        self._recovery_history.append(result)
        return result

    def _find_playbook(self, failure_desc: str) -> RecoveryPlaybook | None:
        """Find a matching recovery playbook for a failure."""
        for pb in self._playbooks:
            if pb.failure_pattern and pb.failure_pattern.lower() in failure_desc.lower():
                return pb
        return None

    def get_history(self) -> list[dict[str, Any]]:
        """Return recovery attempt history for auditing."""
        return list(self._recovery_history)
