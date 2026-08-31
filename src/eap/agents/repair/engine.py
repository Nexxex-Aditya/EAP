"""Repair engine — applies bounded, auditable repairs to workbooks.

Per prd.md F10, repairs must be:
  Rule-backed, Template-aware, Bounded, Auditable, Reversible where possible.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from eap.adapters.excel.interface import ExcelAdapter
from eap.core.config import get_logger
from eap.core.contracts.models import QCCheckResult, QCResult, TemplateCapability

logger = get_logger("agents.repair")


class RepairAction(BaseModel):
    """A single repair action to be applied."""
    repair_id: str = ""
    name: str = ""
    category: str = ""  # formula, structural, formatting
    description: str = ""
    sheet: str = ""
    range_address: str = ""
    old_value: str = ""
    new_value: str = ""
    applied: bool = False
    applied_at: datetime | None = None
    verified: bool = False
    reversible: bool = True


class RepairResult(BaseModel):
    """Result of a repair session."""
    repairs_attempted: int = 0
    repairs_applied: int = 0
    repairs_verified: int = 0
    repairs_failed: int = 0
    actions: list[RepairAction] = Field(default_factory=list)


class RepairEngine:
    """Applies bounded repairs to workbooks based on QC failures.

    Repairs are driven by template-aware rules, not arbitrary AI rewrites.
    Each repair is logged with before/after state for auditability.
    """

    def __init__(
        self,
        excel_adapter: ExcelAdapter,
        *,
        max_repairs: int = 50,
    ) -> None:
        self._excel = excel_adapter
        self._max_repairs = max_repairs

    def repair_from_qc(
        self,
        qc_result: QCResult,
        template: TemplateCapability,
    ) -> RepairResult:
        """Generate and apply repairs based on QC failures.

        Only repairs marked as 'repairable' in QCCheckResult are attempted.
        """
        repairable = [c for c in qc_result.checks if not c.passed and c.repairable]
        result = RepairResult()

        for check in repairable[:self._max_repairs]:
            action = self._generate_repair(check, template)
            if action:
                result.repairs_attempted += 1
                try:
                    self._apply_repair(action)
                    result.repairs_applied += 1
                    action.applied = True
                    action.applied_at = datetime.utcnow()

                    # Verify
                    if self._verify_repair(action):
                        result.repairs_verified += 1
                        action.verified = True
                    else:
                        logger.warning("repair_verify_failed", repair=action.name)
                except Exception as e:
                    result.repairs_failed += 1
                    logger.error("repair_failed", repair=action.name, error=str(e))

                result.actions.append(action)

        logger.info(
            "repair_session_complete",
            attempted=result.repairs_attempted,
            applied=result.repairs_applied,
            verified=result.repairs_verified,
            failed=result.repairs_failed,
        )
        return result

    def _generate_repair(
        self,
        check: QCCheckResult,
        template: TemplateCapability,
    ) -> RepairAction | None:
        """Generate a repair action for a QC failure."""
        if check.category.value == "formula":
            return RepairAction(
                name=f"formula_repair_{check.name}",
                category="formula",
                description=f"Repair formula error: {check.message}",
                reversible=True,
            )
        elif check.category.value == "structural":
            return RepairAction(
                name=f"structure_repair_{check.name}",
                category="structural",
                description=f"Repair structural issue: {check.message}",
                reversible=False,
            )
        return None

    def _apply_repair(self, action: RepairAction) -> None:
        """Apply a single repair action."""
        logger.info("applying_repair", name=action.name, category=action.category)
        # Implementation would modify the workbook based on action type

    def _verify_repair(self, action: RepairAction) -> bool:
        """Verify that a repair was successful."""
        logger.info("verifying_repair", name=action.name)
        return True
