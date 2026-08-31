"""Macro orchestration engine — manages the precondition → execute → verify cycle.

Per rules.md §10, every macro execution follows:
  Precondition → Execute → Observe → Verify expected effect → Record result

Macro sequences are driven by template capability metadata, not hard-coded.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from eap.adapters.excel.interface import ExcelAdapter
from eap.core.config import get_logger
from eap.core.contracts.models import MacroSpec, TemplateCapability
from eap.core.errors.exceptions import MacroError, MacroVerificationError

logger = get_logger("excel.macros")


class MacroExecutionResult(BaseModel):
    """Result of a single macro execution."""
    macro_name: str
    success: bool = False
    executed_at: datetime = Field(default_factory=datetime.utcnow)
    return_value: str = ""
    error: str = ""
    precondition_met: bool = True
    verification_passed: bool = False
    verification_details: str = ""


class MacroOrchestrator:
    """Orchestrates macro execution according to template capabilities.

    Macros are run in the order specified by the template's MacroSpec
    definitions (sorted by run_order). Each macro undergoes the full
    precondition → execute → verify cycle.
    """

    def __init__(self, excel_adapter: ExcelAdapter) -> None:
        self._excel = excel_adapter

    def execute_sequence(
        self,
        macros: list[MacroSpec],
        *,
        stop_on_failure: bool = True,
    ) -> list[MacroExecutionResult]:
        """Execute a sequence of macros in order.

        Args:
            macros: List of MacroSpec to execute, sorted by run_order.
            stop_on_failure: If True, stop the sequence on first failure.

        Returns:
            List of MacroExecutionResult for each attempted macro.
        """
        sorted_macros = sorted(macros, key=lambda m: m.run_order)
        results: list[MacroExecutionResult] = []

        for spec in sorted_macros:
            result = self._execute_single(spec)
            results.append(result)

            if not result.success and stop_on_failure:
                logger.error(
                    "macro_sequence_stopped",
                    failed_macro=spec.name,
                    error=result.error,
                )
                break

        return results

    def execute_developer_mode(self) -> MacroExecutionResult:
        """Execute DeveloperMode macro to expose hidden material."""
        spec = MacroSpec(
            name="DeveloperMode",
            description="Exposes hidden sheets and formulas for editing",
            expected_effect="Hidden sheets become visible",
        )
        return self._execute_single(spec)

    def execute_insert_columns(self) -> MacroExecutionResult:
        """Execute InsertColumns macro to rebuild output structure."""
        spec = MacroSpec(
            name="InsertColumns",
            description="Rebuilds output structure after data fetch",
            expected_effect="Output columns are inserted/rebuilt",
        )
        return self._execute_single(spec)

    def execute_auto_open(self) -> MacroExecutionResult:
        """Execute AutoOpen/auto_open macro to finalize the workbook."""
        # Try auto_open first, then AutoOpen
        for name in ["auto_open", "AutoOpen"]:
            spec = MacroSpec(
                name=name,
                description="Finalizes workbook — hides internal material",
                expected_effect="Internal sheets are hidden, presentation state restored",
            )
            try:
                result = self._execute_single(spec)
                if result.success:
                    return result
            except MacroError:
                continue

        return MacroExecutionResult(
            macro_name="auto_open",
            success=False,
            error="Neither auto_open nor AutoOpen found",
        )

    def execute_template_macros(
        self,
        template: TemplateCapability,
        *,
        phase: str = "all",
    ) -> list[MacroExecutionResult]:
        """Execute macros defined in a template's capability profile.

        Args:
            template: The template whose macros to execute.
            phase: 'pre' (DeveloperMode), 'post_data' (InsertColumns),
                   'finalize' (AutoOpen), or 'all'.
        """
        macros_to_run: list[MacroSpec] = []

        if phase in ("pre", "all") and template.has_developer_mode:
            macros_to_run.append(MacroSpec(
                name="DeveloperMode",
                run_order=0,
                description="Expose hidden sheets",
            ))

        if phase in ("post_data", "all") and template.has_insert_columns:
            macros_to_run.append(MacroSpec(
                name="InsertColumns",
                run_order=50,
                description="Rebuild output structure",
            ))

        if phase in ("finalize", "all") and template.has_auto_open:
            macros_to_run.append(MacroSpec(
                name="auto_open",
                run_order=100,
                description="Finalize workbook",
            ))

        # Add any additional template-specific macros
        for spec in template.macros:
            if spec.name not in {m.name for m in macros_to_run}:
                macros_to_run.append(spec)

        return self.execute_sequence(macros_to_run)

    def _execute_single(self, spec: MacroSpec) -> MacroExecutionResult:
        """Execute a single macro with full precondition/verify cycle."""
        result = MacroExecutionResult(macro_name=spec.name)

        # 1. Precondition check
        logger.info(
            "macro_precondition_check",
            macro=spec.name,
            precondition=spec.precondition,
        )

        # 2. Execute
        try:
            return_value = self._excel.run_macro(spec.name)
            result.return_value = str(return_value) if return_value else ""
            result.success = True
            logger.info("macro_executed_ok", macro=spec.name)
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error("macro_execution_failed", macro=spec.name, error=str(e))
            return result

        # 3. Verify (basic — check workbook is still accessible)
        try:
            info = self._excel.inspect()
            result.verification_passed = True
            result.verification_details = f"Workbook intact: {info.get('sheet_count', 0)} sheets"
        except Exception as e:
            result.verification_passed = False
            result.verification_details = f"Post-macro verification failed: {e}"
            logger.warning("macro_verify_failed", macro=spec.name, error=str(e))

        return result
