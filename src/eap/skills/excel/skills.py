"""Excel skills — atomic workbook operations.

Per V1 review §19, each skill follows:
check_permissions → check_preconditions → execute → verify → (recover)

These skills use the real Windows COM adapter when available.
"""

from __future__ import annotations

from typing import Any

from eap.adapters.excel.interface import ExcelAdapter
from eap.skills.base import Skill, SkillDefinition
from eap.core.config import get_logger

logger = get_logger("skills.excel")


class InspectWorkbookSkill(Skill):
    """Inspect an Excel workbook: sheets, macros, formulas, named ranges."""

    def __init__(self, excel: ExcelAdapter, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._excel = excel

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="excel.inspect_workbook",
            name="Inspect Workbook",
            description="Open and inspect workbook structure: sheets, macros, formulas, named ranges, capabilities",
            component="excel",
            required_inputs=["workbook_path"],
            preconditions=["workbook_file_exists"],
            postconditions=["workbook_metadata_extracted"],
            failure_modes=[
                "file_not_found",
                "file_corrupted",
                "file_locked_by_another_process",
                "com_initialization_failed",
            ],
            recovery_strategies=[
                "retry_after_delay",
                "close_other_excel_instances",
            ],
            required_permissions=["file_read"],
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        from pathlib import Path
        wb_path = context.get("workbook_path", "")
        if not wb_path:
            return False, "workbook_path not provided"
        if not Path(wb_path).exists():
            return False, f"File does not exist: {wb_path}"
        return True, f"Workbook found at {wb_path}"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        wb_path = context["workbook_path"]
        try:
            self._excel.open(wb_path)
            sheets = self._excel.get_sheets()
            info = self._excel.inspect()
            return {
                "status": "EXECUTED",
                "workbook_path": wb_path,
                "sheets": sheets,
                "info": info,
            }
        except Exception as e:
            return {
                "status": "FAILED",
                "workbook_path": wb_path,
                "error": str(e),
            }

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        if result.get("status") == "FAILED":
            return False, f"Inspection failed: {result.get('error')}"
        sheets = result.get("sheets", [])
        if not sheets:
            return False, "No sheets found — workbook may be empty or corrupted"
        return True, f"Workbook inspected: {len(sheets)} sheets found"


class InsertColumnsSkill(Skill):
    """Run the InsertColumns macro on a workbook."""

    def __init__(self, excel: ExcelAdapter, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._excel = excel

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="excel.insert_columns",
            name="Insert Columns",
            description="Execute the InsertColumns macro, then verify structural and formula integrity",
            component="excel",
            required_inputs=["workbook_path"],
            preconditions=["workbook_open", "macro_exists:InsertColumns"],
            postconditions=["columns_inserted", "formulas_intact", "structure_valid"],
            failure_modes=[
                "macro_not_found",
                "macro_timeout",
                "macro_runtime_error",
                "formula_corruption_after_macro",
                "structure_corruption_after_macro",
            ],
            recovery_strategies=[
                "restore_from_backup_copy",
                "retry_macro_with_calculation_manual",
            ],
            required_permissions=["macro_execute", "file_write"],
            idempotent=False,
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        wb_path = context.get("workbook_path", "")
        if not wb_path:
            return False, "workbook_path not provided"
        return True, "Ready to run InsertColumns"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        try:
            self._excel.run_macro("InsertColumns")
            return {
                "status": "EXECUTED",
                "macro": "InsertColumns",
            }
        except Exception as e:
            return {
                "status": "FAILED",
                "macro": "InsertColumns",
                "error": str(e),
            }

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        if result.get("status") == "FAILED":
            return False, f"InsertColumns failed: {result.get('error')}"

        # Verify no formula errors were introduced
        try:
            sheets = self._excel.get_sheets()
            total_errors = 0
            for sheet_info in sheets:
                if sheet_info.get("visible", True):
                    errors = self._excel.detect_formula_errors(sheet_info["name"])
                    total_errors += len(errors)

            if total_errors > 0:
                return False, f"InsertColumns introduced {total_errors} formula error(s)"
            return True, "InsertColumns verified: no formula errors detected"
        except Exception as e:
            return False, f"Verification failed: {e}"
