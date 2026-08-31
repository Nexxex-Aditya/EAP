"""Discover skills — atomic browser operations for NielsenIQ Discover.

Per V1 review §19, each skill follows the full lifecycle:
check_permissions → check_preconditions → execute → verify → (recover)

Status: PARTIALLY_IMPLEMENTED.
These skills define the correct contract and verification requirements.
Full browser automation depends on a live Discover instance.
"""

from __future__ import annotations

from typing import Any

from eap.adapters.browser.interface import BrowserAdapter
from eap.skills.base import Skill, SkillDefinition, SkillStatus
from eap.core.config import get_logger

logger = get_logger("skills.discover")


class LoginSkill(Skill):
    """Authenticate to NielsenIQ Discover."""

    def __init__(self, browser: BrowserAdapter, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._browser = browser

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="discover.login",
            name="Discover Login",
            description="Authenticate to NielsenIQ Discover and establish a valid session",
            component="discover",
            required_inputs=["discover_url"],
            preconditions=["browser_session_open"],
            postconditions=["session_authenticated", "dashboard_visible"],
            failure_modes=[
                "invalid_credentials",
                "mfa_required",
                "session_timeout",
                "network_error",
                "captcha_required",
            ],
            recovery_strategies=[
                "retry_with_fresh_session",
                "escalate_to_human_for_mfa",
            ],
            required_permissions=["browser_navigate"],
            idempotent=False,
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        if "discover_url" not in context:
            return False, "discover_url not provided in context"
        return True, "Browser session available"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        url = context["discover_url"]
        # Real implementation would navigate and authenticate.
        # Marking honestly per V1 review §1.
        return {
            "status": "REQUIRES_HUMAN",
            "reason": "Login requires real credentials and possibly MFA — cannot be fully automated without live environment",
            "url": url,
        }

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        # Real verification: check for authenticated session indicator in DOM
        if result.get("status") == "REQUIRES_HUMAN":
            return False, "Login not verified — requires human interaction"
        return False, "Login verification NOT_IMPLEMENTED for this environment"


class SelectFactsSkill(Skill):
    """Select facts (measures) in the Discover query builder."""

    def __init__(self, browser: BrowserAdapter, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._browser = browser

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="discover.select_facts",
            name="Select Facts",
            description="Select requested facts/measures in Discover, verifying each selection against available options",
            component="discover",
            required_inputs=["resolved_facts"],
            preconditions=["session_authenticated", "dataset_configured"],
            postconditions=["facts_selected", "facts_verified_in_ui"],
            failure_modes=[
                "fact_not_found_in_ui",
                "ambiguous_fact_match",
                "fact_panel_not_visible",
                "ui_element_stale",
            ],
            recovery_strategies=[
                "refresh_panel_and_retry",
                "search_by_partial_match",
                "escalate_ambiguous_to_human",
            ],
            required_permissions=["browser_navigate", "browser_click"],
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        if "resolved_facts" not in context:
            return False, "resolved_facts not provided in context"
        facts = context["resolved_facts"]
        if not facts:
            return False, "resolved_facts is empty"
        return True, f"{len(facts)} facts to select"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        facts = context["resolved_facts"]
        # Real implementation would:
        # 1. Open the Facts panel in Discover
        # 2. For each fact: search, locate, select
        # 3. Record what was actually selected
        return {
            "status": "NOT_IMPLEMENTED",
            "reason": "Requires live Discover session with browser automation",
            "requested_facts": facts,
            "selected_facts": [],
        }

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        if result.get("status") == "NOT_IMPLEMENTED":
            return False, "Facts selection NOT_IMPLEMENTED — no live environment"
        # Real verification: read the Facts panel state and compare
        return False, "Facts verification NOT_IMPLEMENTED"


class SelectProductsSkill(Skill):
    """Select products in the Discover query builder."""

    def __init__(self, browser: BrowserAdapter, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._browser = browser

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="discover.select_products",
            name="Select Products",
            description="Navigate product hierarchy and select requested products in Discover",
            component="discover",
            required_inputs=["resolved_products"],
            preconditions=["session_authenticated", "dataset_configured"],
            postconditions=["products_selected", "products_verified_in_ui"],
            failure_modes=[
                "product_not_found",
                "hierarchy_navigation_failed",
                "drill_path_mismatch",
            ],
            recovery_strategies=[
                "try_alternate_drill_path",
                "search_by_name",
                "escalate_to_human",
            ],
            required_permissions=["browser_navigate", "browser_click"],
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        if "resolved_products" not in context:
            return False, "resolved_products not provided"
        return True, "Products ready for selection"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        products = context["resolved_products"]
        return {
            "status": "NOT_IMPLEMENTED",
            "reason": "Requires live Discover session",
            "requested_products": products,
            "selected_products": [],
        }

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        if result.get("status") == "NOT_IMPLEMENTED":
            return False, "Products selection NOT_IMPLEMENTED"
        return False, "Products verification NOT_IMPLEMENTED"


class SelectMarketsSkill(Skill):
    """Select markets in the Discover query builder."""

    def __init__(self, browser: BrowserAdapter, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._browser = browser

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="discover.select_markets",
            name="Select Markets",
            description="Select requested markets in Discover, distinguishing Total ALDI from ALDI VIC etc.",
            component="discover",
            required_inputs=["resolved_markets"],
            preconditions=["session_authenticated", "dataset_configured"],
            postconditions=["markets_selected", "markets_verified_in_ui"],
            failure_modes=[
                "market_not_found",
                "ambiguous_market_name",
                "market_panel_not_visible",
            ],
            recovery_strategies=[
                "search_by_exact_name",
                "escalate_ambiguous_to_human",
            ],
            required_permissions=["browser_navigate", "browser_click"],
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        if "resolved_markets" not in context:
            return False, "resolved_markets not provided"
        return True, "Markets ready for selection"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        markets = context["resolved_markets"]
        return {
            "status": "NOT_IMPLEMENTED",
            "reason": "Requires live Discover session",
            "requested_markets": markets,
            "selected_markets": [],
        }

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        if result.get("status") == "NOT_IMPLEMENTED":
            return False, "Markets selection NOT_IMPLEMENTED"
        return False, "Markets verification NOT_IMPLEMENTED"


class SelectPeriodsSkill(Skill):
    """Select periods in the Discover query builder.

    Per V1 review §12: Periods are one of the highest-risk areas.
    The system must preserve exact date semantics and never silently shift dates.
    """

    def __init__(self, browser: BrowserAdapter, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._browser = browser

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="discover.select_periods",
            name="Select Periods",
            description="Select requested periods in Discover, preserving exact date semantics",
            component="discover",
            required_inputs=["resolved_periods"],
            preconditions=["session_authenticated", "dataset_configured"],
            postconditions=["periods_selected", "periods_verified_in_ui"],
            failure_modes=[
                "period_not_available",
                "ambiguous_period_expression",
                "date_format_mismatch",
                "rolling_period_unavailable",
            ],
            recovery_strategies=[
                "try_closest_available_period",
                "escalate_ambiguous_to_human",
            ],
            required_permissions=["browser_navigate", "browser_click"],
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        if "resolved_periods" not in context:
            return False, "resolved_periods not provided"
        return True, "Periods ready for selection"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        periods = context["resolved_periods"]
        return {
            "status": "NOT_IMPLEMENTED",
            "reason": "Requires live Discover session",
            "requested_periods": periods,
            "selected_periods": [],
        }

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        if result.get("status") == "NOT_IMPLEMENTED":
            return False, "Periods selection NOT_IMPLEMENTED"
        return False, "Periods verification NOT_IMPLEMENTED"
