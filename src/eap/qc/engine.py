"""QC engine — runs quality control checks across all categories.

Per prd.md F11, QC categories:
  Numerical, Formula, Structural, Textual, Design/Format,
  Workbook Integrity, Output Naming/Location.

Per rules.md §14: No declaring success without QC.
"""

from __future__ import annotations

from typing import Any

from eap.adapters.excel.interface import ExcelAdapter
from eap.core.config import get_logger
from eap.core.contracts.models import (
    QCCategory,
    QCCheckResult,
    QCResult,
    TemplateCapability,
    DiscoverPlan,
)

logger = get_logger("qc.engine")


class QCEngine:
    """Runs quality control checks on a completed report workbook.

    Each check produces a QCCheckResult. The aggregate QCResult
    determines whether the report passes.
    """

    def __init__(self, excel_adapter: ExcelAdapter) -> None:
        self._excel = excel_adapter

    def run_full_qc(
        self,
        template: TemplateCapability,
        plan: DiscoverPlan | None = None,
        *,
        categories: list[QCCategory] | None = None,
    ) -> QCResult:
        """Run all applicable QC checks.

        Args:
            template: The template capability profile.
            plan: The Discover plan for dimension verification.
            categories: Specific categories to check. None = all.
        """
        all_categories = categories or list(QCCategory)
        checks: list[QCCheckResult] = []

        for category in all_categories:
            try:
                category_checks = self._run_category(category, template, plan)
                checks.extend(category_checks)
            except Exception as e:
                checks.append(QCCheckResult(
                    category=category,
                    name=f"{category.value}_error",
                    passed=False,
                    message=f"QC category error: {e}",
                    severity="error",
                ))

        result = QCResult(checks=checks)
        result.compute_summary()

        logger.info(
            "qc_complete",
            total=result.total_checks,
            passed=result.passed_count,
            failed=result.failed_count,
            warnings=result.warning_count,
            overall=result.passed,
        )
        return result

    def _run_category(
        self,
        category: QCCategory,
        template: TemplateCapability,
        plan: DiscoverPlan | None,
    ) -> list[QCCheckResult]:
        """Run checks for a specific category."""
        match category:
            case QCCategory.NUMERICAL:
                return self._check_numerical(template, plan)
            case QCCategory.FORMULA:
                return self._check_formulas(template)
            case QCCategory.STRUCTURAL:
                return self._check_structural(template)
            case QCCategory.TEXTUAL:
                return self._check_textual(template)
            case QCCategory.VISUAL:
                return self._check_visual(template)
            case QCCategory.INTEGRITY:
                return self._check_integrity(template)
            case QCCategory.NAMING:
                return self._check_naming(template)
            case _:
                return []

    def _check_numerical(
        self, template: TemplateCapability, plan: DiscoverPlan | None
    ) -> list[QCCheckResult]:
        """Numerical QC: check data presence and reasonability."""
        checks: list[QCCheckResult] = []

        # Check that output sheets have data
        for sheet_name in template.output_sheets:
            try:
                data = self._excel.read_range(sheet_name, "A1:A5")
                has_data = any(
                    cell is not None
                    for row in data
                    for cell in row
                )
                checks.append(QCCheckResult(
                    category=QCCategory.NUMERICAL,
                    name=f"data_presence_{sheet_name}",
                    passed=has_data,
                    message=f"Output sheet '{sheet_name}' {'has' if has_data else 'lacks'} data",
                    severity="error",
                ))
            except Exception as e:
                checks.append(QCCheckResult(
                    category=QCCategory.NUMERICAL,
                    name=f"data_check_error_{sheet_name}",
                    passed=False,
                    message=str(e),
                    severity="error",
                ))

        return checks

    def _check_formulas(self, template: TemplateCapability) -> list[QCCheckResult]:
        """Formula QC: detect broken formulas (#REF!, #VALUE!, etc.)."""
        checks: list[QCCheckResult] = []

        sheets = self._excel.get_sheets()
        for sheet_info in sheets:
            if not sheet_info.get("visible", True):
                continue

            errors = self._excel.detect_formula_errors(sheet_info["name"])
            if errors:
                checks.append(QCCheckResult(
                    category=QCCategory.FORMULA,
                    name=f"formula_errors_{sheet_info['name']}",
                    passed=False,
                    message=f"{len(errors)} formula error(s) in '{sheet_info['name']}'",
                    evidence=str(errors[:5]),
                    severity="error",
                    repairable=True,
                ))
            else:
                checks.append(QCCheckResult(
                    category=QCCategory.FORMULA,
                    name=f"formula_clean_{sheet_info['name']}",
                    passed=True,
                    message=f"No formula errors in '{sheet_info['name']}'",
                ))

        return checks

    def _check_structural(self, template: TemplateCapability) -> list[QCCheckResult]:
        """Structural QC: verify expected sheets, ranges, dimensions."""
        checks: list[QCCheckResult] = []

        # Verify expected sheets exist
        actual_sheets = {s["name"] for s in self._excel.get_sheets()}

        for expected_sheet in template.output_sheets:
            checks.append(QCCheckResult(
                category=QCCategory.STRUCTURAL,
                name=f"sheet_exists_{expected_sheet}",
                passed=expected_sheet in actual_sheets,
                message=f"Sheet '{expected_sheet}' {'found' if expected_sheet in actual_sheets else 'MISSING'}",
                severity="error",
            ))

        # Verify sheet count is reasonable
        sheet_count = len(actual_sheets)
        checks.append(QCCheckResult(
            category=QCCategory.STRUCTURAL,
            name="sheet_count",
            passed=sheet_count >= len(template.sheets) if template.sheets else sheet_count > 0,
            message=f"Workbook has {sheet_count} sheets",
        ))

        return checks

    def _check_textual(self, template: TemplateCapability) -> list[QCCheckResult]:
        """Textual QC: verify labels, headers, naming."""
        checks: list[QCCheckResult] = []

        # Basic check: workbook has a name
        try:
            info = self._excel.inspect()
            name = info.get("name", "")
            checks.append(QCCheckResult(
                category=QCCategory.TEXTUAL,
                name="workbook_named",
                passed=bool(name),
                message=f"Workbook name: '{name}'",
            ))
        except Exception:
            pass

        return checks

    def _check_visual(self, template: TemplateCapability) -> list[QCCheckResult]:
        """Visual QC: check formatting and design compliance.

        Status: NOT_IMPLEMENTED.
        Per V1 review §1: Do not return passed=True for unimplemented checks.
        """
        return [QCCheckResult(
            category=QCCategory.VISUAL,
            name="visual_not_implemented",
            passed=False,
            message="Visual QC is NOT_IMPLEMENTED. Column widths, formatting, chart integrity, ### detection pending.",
            severity="info",
        )]

    def _check_integrity(self, template: TemplateCapability) -> list[QCCheckResult]:
        """Integrity QC: verify workbook can be opened, saved, and re-read."""
        checks: list[QCCheckResult] = []

        try:
            validation = self._excel.validate()
            checks.append(QCCheckResult(
                category=QCCategory.INTEGRITY,
                name="workbook_integrity",
                passed=validation.get("valid", False),
                message=f"Integrity check: {'passed' if validation.get('valid') else 'failed'}",
                evidence=str(validation.get("errors", [])[:3]),
                severity="error",
            ))
        except Exception as e:
            checks.append(QCCheckResult(
                category=QCCategory.INTEGRITY,
                name="integrity_error",
                passed=False,
                message=str(e),
                severity="error",
            ))

        return checks

    def _check_naming(self, template: TemplateCapability) -> list[QCCheckResult]:
        """Naming QC: verify output file naming conventions.

        Status: NOT_IMPLEMENTED.
        Per V1 review §1: Do not return passed=True for unimplemented checks.
        """
        return [QCCheckResult(
            category=QCCategory.NAMING,
            name="naming_not_implemented",
            passed=False,
            message="Naming convention QC is NOT_IMPLEMENTED.",
            severity="info",
        )]
