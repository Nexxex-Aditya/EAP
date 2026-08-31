"""Report planner — builds a complete ReportPlan from a ReportRequest.

The planner is the bridge between the request intake and execution.
It selects the template, resolves terms, builds the DiscoverPlan,
and produces the ReportPlan that the graph orchestrator executes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eap.agents.resolver.resolver import SemanticResolver, PeriodResolver
from eap.core.config import EAPSettings, get_logger
from eap.core.contracts.models import (
    DiscoverPlan,
    FormatConfig,
    LayoutConfig,
    ReportPlan,
    ReportRequest,
    ResolutionResult,
    ConfidenceLevel,
    TemplateCapability,
)
from eap.ingestion.template_discovery.registry import TemplateRegistry
from eap.core.errors.exceptions import SemanticError, ConfigurationError

logger = get_logger("agents.planner")


class ReportPlanner:
    """Builds a complete ReportPlan from a ReportRequest."""

    def __init__(
        self,
        template_registry: TemplateRegistry,
        resolver: SemanticResolver,
        settings: EAPSettings | None = None,
    ) -> None:
        self._registry = template_registry
        self._resolver = resolver
        self._period_resolver = PeriodResolver(resolver)
        self._settings = settings or EAPSettings()

    def build_plan(
        self,
        request: ReportRequest,
        *,
        available_facts: list[str] | None = None,
        available_products: list[str] | None = None,
        available_markets: list[str] | None = None,
        available_periods: list[str] | None = None,
    ) -> ReportPlan:
        """Build a ReportPlan from a ReportRequest.

        This is the main planning function. It:
        1. Selects the best template
        2. Resolves all business terms
        3. Builds the DiscoverPlan
        4. Determines the macro sequence
        5. Flags anything requiring approval
        """
        logger.info("building_plan", request_id=request.request_id)

        # 1. Select template
        template = self._select_template(request)
        if template is None:
            raise ConfigurationError("No suitable template found")

        # 2. Resolve facts
        resolved_facts: list[ResolutionResult] = []
        if request.facts and available_facts:
            resolved_facts = self._resolver.resolve_batch(
                request.facts, available_facts
            )

        # 3. Resolve periods
        resolved_periods: list[ResolutionResult] = []
        if request.periods and available_periods:
            resolved_periods = [
                self._period_resolver.resolve_period_expression(p, available_periods)
                for p in request.periods
            ]

        # 4. Build DiscoverPlan
        discover_plan = DiscoverPlan(
            request_id=request.request_id,
            region=request.region,
            offering="Retail Measurement - FMCG",
            dataset=self._resolve_if_available(request.dataset_hint, []),
            view=self._resolve_if_available(request.view_hint, []),
            facts=resolved_facts,
            format_config=request.format_config or FormatConfig(),
            layout_config=request.layout_config or template.default_layout or LayoutConfig(),
            start_cell=template.output_start_cell,
        )

        # Check if approval needed
        all_resolutions = resolved_facts + resolved_periods
        needs_approval = self._resolver.any_requires_approval(all_resolutions)
        discover_plan.requires_approval = needs_approval
        discover_plan.unresolved_items = [r for r in all_resolutions if r.requires_approval]

        # 5. Build macro sequence
        macro_sequence: list[str] = []
        if template.has_developer_mode:
            macro_sequence.append("DeveloperMode")
        if template.has_insert_columns:
            macro_sequence.append("InsertColumns")
        if template.has_auto_open:
            macro_sequence.append("auto_open")

        # 6. Build workspace path
        workspace = self._settings.workspace_root / request.request_id

        plan = ReportPlan(
            request_id=request.request_id,
            template_id=template.template_id,
            discover_plan_id=discover_plan.plan_id,
            request=request,
            template=template,
            discover_plan=discover_plan,
            workspace_path=str(workspace),
            macro_sequence=macro_sequence,
            qc_profile=template.qc_profile,
            approved=not needs_approval,
        )

        logger.info(
            "plan_built",
            plan_id=plan.plan_id,
            template=template.name,
            needs_approval=needs_approval,
            unresolved=len(discover_plan.unresolved_items),
        )
        return plan

    def _select_template(self, request: ReportRequest) -> TemplateCapability | None:
        """Select the best template for the request."""
        return self._registry.find_best_match(
            template_hint=request.template_hint,
        )

    def _resolve_if_available(
        self, hint: str, choices: list[str]
    ) -> ResolutionResult | None:
        """Resolve a hint against choices, or return None."""
        if not hint:
            return None
        if not choices:
            return ResolutionResult(requested=hint, resolved=hint, confidence=0.5)
        return self._resolver.resolve(hint, choices)
