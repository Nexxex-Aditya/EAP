"""Windows Excel COM adapter — implements ExcelAdapter using pywin32.

Per rules.md §9:
- Never mutate the original template
- Create a versioned working copy
- Preserve source hash
- Verify macro effects
- Re-open and validate final workbook

This adapter isolates all Windows-specific COM code behind the abstract
ExcelAdapter interface so domain logic never imports pywin32.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from eap.adapters.excel.interface import ExcelAdapter
from eap.core.config import get_logger
from eap.core.errors.exceptions import (
    ExcelError,
    MacroError,
    MacroNotFoundError,
    MacroVerificationError,
    WorkbookOpenError,
    WorkbookSaveError,
)
from eap.ingestion.workbook_scanner.scanner import compute_file_hash

logger = get_logger("adapters.excel.windows_com")


class WindowsExcelCOMAdapter(ExcelAdapter):
    """Excel adapter using Windows COM automation (pywin32).

    Must be used from a Windows environment with Excel installed.
    COM operations are synchronous and single-threaded per design.
    """

    def __init__(self, *, visible: bool = False, timeout_seconds: int = 120) -> None:
        self._visible = visible
        self._timeout_seconds = timeout_seconds
        self._xl: Any = None
        self._wb: Any = None
        self._file_path: str = ""
        self._com_initialized = False

    def _ensure_excel(self) -> Any:
        """Ensure Excel COM application is running."""
        if self._xl is None:
            try:
                import pythoncom  # type: ignore[import-untyped]
                import win32com.client  # type: ignore[import-untyped]

                if not self._com_initialized:
                    pythoncom.CoInitialize()
                    self._com_initialized = True

                self._xl = win32com.client.Dispatch("Excel.Application")
                self._xl.Visible = self._visible
                self._xl.DisplayAlerts = False
                logger.info("excel_com_started", visible=self._visible)
            except ImportError as e:
                raise ExcelError("pywin32 not available — Windows required") from e
            except Exception as e:
                raise ExcelError(f"Failed to start Excel: {e}") from e
        return self._xl

    def open(self, file_path: str | Path, *, read_only: bool = False) -> None:
        """Open an Excel workbook."""
        xl = self._ensure_excel()
        path = Path(file_path).resolve()
        if not path.exists():
            raise WorkbookOpenError(f"File not found: {path}")

        try:
            self._wb = xl.Workbooks.Open(str(path), ReadOnly=read_only)
            self._file_path = str(path)
            logger.info("workbook_opened", path=str(path), read_only=read_only)
        except Exception as e:
            raise WorkbookOpenError(f"Failed to open: {e}") from e

    def create_working_copy(self, source: str | Path, destination: str | Path) -> str:
        """Create a versioned working copy of a template."""
        src = Path(source).resolve()
        dst = Path(destination).resolve()

        if not src.exists():
            raise WorkbookOpenError(f"Source not found: {src}")

        # Create destination directory
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(src, dst)

        # Verify copy hash matches source
        src_hash = compute_file_hash(src)
        dst_hash = compute_file_hash(dst)
        if src_hash != dst_hash:
            raise ExcelError("Working copy hash mismatch")

        logger.info(
            "working_copy_created",
            source=str(src),
            destination=str(dst),
            hash=src_hash,
        )
        return str(dst)

    def inspect(self) -> dict[str, Any]:
        """Inspect the currently open workbook."""
        wb = self._require_workbook()
        info: dict[str, Any] = {
            "name": wb.Name,
            "path": wb.FullName,
            "sheet_count": wb.Sheets.Count,
            "sheets": [],
            "named_ranges": [],
            "macros": [],
        }

        # Sheets
        for i in range(1, wb.Sheets.Count + 1):
            ws = wb.Sheets(i)
            info["sheets"].append({
                "name": ws.Name,
                "index": i - 1,
                "visible": ws.Visible == -1,
            })

        # Named ranges
        try:
            for nm in wb.Names:
                info["named_ranges"].append({
                    "name": nm.Name,
                    "value": str(nm.Value),
                })
        except Exception:
            pass

        return info

    def read_range(self, sheet: str, range_address: str) -> list[list[Any]]:
        """Read values from a range."""
        wb = self._require_workbook()
        try:
            ws = wb.Sheets(sheet)
            rng = ws.Range(range_address)
            values = rng.Value

            # Normalize to 2D list
            if values is None:
                return [[]]
            if not isinstance(values, tuple):
                return [[values]]
            return [list(row) if isinstance(row, tuple) else [row] for row in values]
        except Exception as e:
            raise ExcelError(f"Read range failed: {e}") from e

    def write_range(self, sheet: str, range_address: str, values: list[list[Any]]) -> None:
        """Write values to a range."""
        wb = self._require_workbook()
        try:
            ws = wb.Sheets(sheet)
            rng = ws.Range(range_address)
            rng.Value = values
            logger.info("range_written", sheet=sheet, range=range_address)
        except Exception as e:
            raise ExcelError(f"Write range failed: {e}") from e

    def get_sheets(self) -> list[dict[str, Any]]:
        """List all sheets with visibility and basic metadata."""
        wb = self._require_workbook()
        sheets: list[dict[str, Any]] = []
        for i in range(1, wb.Sheets.Count + 1):
            ws = wb.Sheets(i)
            sheets.append({
                "name": ws.Name,
                "index": i - 1,
                "visible": ws.Visible == -1,
                "used_range": str(ws.UsedRange.Address) if ws.UsedRange else "",
            })
        return sheets

    def get_named_ranges(self) -> list[dict[str, str]]:
        """List all named ranges."""
        wb = self._require_workbook()
        ranges: list[dict[str, str]] = []
        try:
            for nm in wb.Names:
                ranges.append({"name": nm.Name, "value": str(nm.Value)})
        except Exception:
            pass
        return ranges

    def get_macros(self) -> list[str]:
        """List available macro names in the workbook."""
        wb = self._require_workbook()
        macros: list[str] = []
        try:
            vb = wb.VBProject
            for comp in vb.VBComponents:
                code = comp.CodeModule
                if code.CountOfLines > 0:
                    text = code.Lines(1, code.CountOfLines)
                    # Extract Sub/Function names
                    for line in text.split("\n"):
                        line = line.strip()
                        if line.lower().startswith("sub ") or line.lower().startswith("public sub "):
                            name = line.split("(")[0].split()[-1]
                            macros.append(name)
        except Exception as e:
            logger.warning("macro_list_failed", error=str(e))
        return macros

    def run_macro(self, macro_name: str, *args: Any) -> Any:
        """Execute a macro by name with precondition/postcondition logging.

        Per rules.md §10: Precondition → Execute → Observe → Verify → Record.
        """
        wb = self._require_workbook()
        xl = self._xl

        logger.info("macro_precondition", macro=macro_name, workbook=wb.Name)

        try:
            if args:
                result = xl.Run(macro_name, *args)
            else:
                result = xl.Run(macro_name)

            logger.info("macro_executed", macro=macro_name, result=str(result)[:200])
            return result
        except Exception as e:
            error_msg = str(e)
            if "cannot find" in error_msg.lower() or "not found" in error_msg.lower():
                raise MacroNotFoundError(f"Macro '{macro_name}' not found") from e
            raise MacroError(f"Macro '{macro_name}' failed: {e}") from e

    def get_formulas(self, sheet: str, range_address: str) -> list[list[str]]:
        """Read formula strings from a range."""
        wb = self._require_workbook()
        try:
            ws = wb.Sheets(sheet)
            rng = ws.Range(range_address)
            formulas = rng.Formula

            if formulas is None:
                return [[""]]
            if not isinstance(formulas, tuple):
                return [[str(formulas)]]
            return [
                [str(cell) if cell else "" for cell in (row if isinstance(row, tuple) else [row])]
                for row in formulas
            ]
        except Exception as e:
            raise ExcelError(f"Get formulas failed: {e}") from e

    def detect_formula_errors(self, sheet: str) -> list[dict[str, Any]]:
        """Scan a sheet for formula errors (#REF!, #VALUE!, #NAME?, etc.)."""
        wb = self._require_workbook()
        errors: list[dict[str, Any]] = []
        error_indicators = {"#REF!", "#VALUE!", "#NAME?", "#DIV/0!", "#NULL!", "#N/A", "#NUM!"}

        try:
            ws = wb.Sheets(sheet)
            used = ws.UsedRange
            if used is None:
                return errors

            values = used.Value
            formulas = used.Formula

            if values and isinstance(values, tuple):
                for r, row in enumerate(values):
                    if not isinstance(row, tuple):
                        row = (row,)
                    for c, val in enumerate(row):
                        if isinstance(val, str) and val in error_indicators:
                            formula = ""
                            if formulas and isinstance(formulas, tuple):
                                try:
                                    f_row = formulas[r]
                                    if isinstance(f_row, tuple):
                                        formula = str(f_row[c])
                                    else:
                                        formula = str(f_row)
                                except (IndexError, TypeError):
                                    pass
                            errors.append({
                                "sheet": sheet,
                                "row": r + 1,
                                "col": c + 1,
                                "error": val,
                                "formula": formula,
                            })
        except Exception as e:
            logger.warning("formula_error_scan_failed", sheet=sheet, error=str(e))

        return errors

    def set_sheet_visibility(self, sheet: str, visible: bool) -> None:
        """Show or hide a worksheet."""
        wb = self._require_workbook()
        try:
            ws = wb.Sheets(sheet)
            ws.Visible = -1 if visible else 0  # xlSheetVisible=-1, xlSheetHidden=0
        except Exception as e:
            raise ExcelError(f"Set visibility failed: {e}") from e

    def validate(self) -> dict[str, Any]:
        """Run structural validation on the workbook."""
        wb = self._require_workbook()
        result: dict[str, Any] = {
            "valid": True,
            "sheet_count": wb.Sheets.Count,
            "errors": [],
            "warnings": [],
        }

        # Check for any formula errors across all visible sheets
        for i in range(1, wb.Sheets.Count + 1):
            ws = wb.Sheets(i)
            if ws.Visible == -1:
                errors = self.detect_formula_errors(ws.Name)
                if errors:
                    result["valid"] = False
                    result["errors"].extend(errors)

        return result

    def save(self, path: str | Path | None = None) -> str:
        """Save the workbook."""
        wb = self._require_workbook()
        try:
            if path:
                save_path = str(Path(path).resolve())
                wb.SaveAs(save_path)
                logger.info("workbook_saved_as", path=save_path)
                return save_path
            else:
                wb.Save()
                logger.info("workbook_saved", path=wb.FullName)
                return wb.FullName
        except Exception as e:
            raise WorkbookSaveError(f"Save failed: {e}") from e

    def close(self) -> None:
        """Close the workbook and release COM resources."""
        try:
            if self._wb:
                self._wb.Close(SaveChanges=False)
                self._wb = None
            if self._xl:
                self._xl.Quit()
                self._xl = None
            if self._com_initialized:
                import pythoncom  # type: ignore[import-untyped]
                pythoncom.CoUninitialize()
                self._com_initialized = False
            logger.info("excel_com_closed")
        except Exception as e:
            logger.warning("excel_close_error", error=str(e))

    def _require_workbook(self) -> Any:
        """Ensure a workbook is open."""
        if self._wb is None:
            raise ExcelError("No workbook is open")
        return self._wb
