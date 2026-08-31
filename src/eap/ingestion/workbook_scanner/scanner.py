"""Workbook scanner — extracts structural metadata from Excel templates.

Per architecture.md §9, a new workbook passes through an ingestion pipeline:
Hash → Structure → Macros → Formulas → Hidden sheets → Output regions
→ Capability inference → Template candidate → Human review → Activated.

This scanner uses pywin32 COM to inspect .xlsb files (which openpyxl
cannot read). It produces a TemplateCapability profile.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from eap.core.config import get_logger
from eap.core.contracts.models import (
    MacroSpec,
    SheetInfo,
    TemplateCapability,
    TemplateStatus,
)
from eap.core.errors.exceptions import ExcelError, WorkbookOpenError

logger = get_logger("ingestion.workbook_scanner")


def compute_file_hash(file_path: str | Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_workbook_com(file_path: str | Path) -> TemplateCapability:
    """Scan an Excel workbook using COM automation to extract capabilities.

    This function opens the workbook in Excel via COM, inspects its
    structure (sheets, macros, named ranges, formulas), and produces
    a TemplateCapability profile.
    """
    file_path = Path(file_path).resolve()
    if not file_path.exists():
        raise WorkbookOpenError(f"File not found: {file_path}")

    file_hash = compute_file_hash(file_path)
    logger.info("scanning_workbook", file=str(file_path), hash=file_hash)

    try:
        import win32com.client  # type: ignore[import-untyped]
        import pythoncom  # type: ignore[import-untyped]

        pythoncom.CoInitialize()
        xl = win32com.client.Dispatch("Excel.Application")
        xl.Visible = False
        xl.DisplayAlerts = False

        wb = xl.Workbooks.Open(str(file_path), ReadOnly=True)

        # --- Extract sheets ---
        sheets: list[SheetInfo] = []
        output_sheets: list[str] = []
        hidden_sheets: list[str] = []

        for i in range(1, wb.Sheets.Count + 1):
            ws = wb.Sheets(i)
            visible = ws.Visible == -1  # xlSheetVisible = -1
            name = ws.Name

            # Count formulas in used range
            formula_count = 0
            has_formulas = False
            try:
                used = ws.UsedRange
                row_count = used.Rows.Count
                col_count = used.Columns.Count
                # Sample check for formulas
                if row_count > 0 and col_count > 0:
                    try:
                        has_formulas_check = used.HasFormula
                        if has_formulas_check is True or has_formulas_check is None:
                            has_formulas = True
                    except Exception:
                        pass
            except Exception:
                row_count = 0
                col_count = 0

            # Named ranges scoped to this sheet
            sheet_names: list[str] = []
            try:
                for nm in ws.Names:
                    sheet_names.append(nm.Name)
            except Exception:
                pass

            # Detect output sheets (heuristic: sheets starting with "Output")
            is_output = "output" in name.lower() or "report" in name.lower()
            if is_output:
                output_sheets.append(name)
            if not visible:
                hidden_sheets.append(name)

            sheets.append(SheetInfo(
                name=name,
                index=i - 1,
                visible=visible,
                has_formulas=has_formulas,
                formula_count=formula_count,
                named_ranges=sheet_names,
                row_count=row_count,
                col_count=col_count,
                is_output_sheet=is_output,
            ))

        # --- Extract macros ---
        macros: list[MacroSpec] = []
        known_macros = {
            "DeveloperMode": "Exposes hidden sheets and formulas for editing",
            "InsertColumns": "Rebuilds output structure after data fetch",
            "auto_open": "Finalizes workbook — hides internal material",
            "AutoOpen": "Finalizes workbook — hides internal material",
        }

        has_developer_mode = False
        has_insert_columns = False
        has_auto_open = False

        try:
            # Try to list VBA project modules
            vb_project = wb.VBProject
            for component in vb_project.VBComponents:
                code_module = component.CodeModule
                if code_module.CountOfLines > 0:
                    code_text = code_module.Lines(1, code_module.CountOfLines)
                    # Search for known macro names
                    for macro_name, desc in known_macros.items():
                        if f"Sub {macro_name}" in code_text or f"sub {macro_name}" in code_text.lower():
                            macros.append(MacroSpec(
                                name=macro_name,
                                description=desc,
                                run_order=len(macros),
                                is_required=True,
                            ))
                            if macro_name.lower() == "developermode":
                                has_developer_mode = True
                            elif macro_name.lower() == "insertcolumns":
                                has_insert_columns = True
                            elif macro_name.lower() in ("auto_open", "autoopen"):
                                has_auto_open = True
        except Exception as e:
            # VBA project may be protected — log and continue
            logger.warning("vba_inspection_failed", error=str(e))

        # --- Extract workbook-level named ranges ---
        workbook_names: list[str] = []
        try:
            for nm in wb.Names:
                workbook_names.append(nm.Name)
        except Exception:
            pass

        # --- Infer methodology from filename ---
        methodology = ""
        fname_lower = file_path.stem.lower()
        if "vlookup" in fname_lower:
            methodology = "VLOOKUP"
        elif "pivot" in fname_lower:
            methodology = "PIVOT"
        elif "ref" in fname_lower:
            methodology = "REF"

        # --- Infer dimension count from filename ---
        dimension_count = 1
        if "2 dim" in fname_lower or "2_dim" in fname_lower or "2-dim" in fname_lower:
            dimension_count = 2

        wb.Close(SaveChanges=False)
        xl.Quit()
        pythoncom.CoUninitialize()

        capability = TemplateCapability(
            name=file_path.stem,
            file_hash=file_hash,
            file_path=str(file_path),
            status=TemplateStatus.CANDIDATE,
            methodology=methodology,
            dimension_count=dimension_count,
            sheets=sheets,
            output_sheets=output_sheets,
            hidden_sheets=hidden_sheets,
            macros=macros,
            has_developer_mode=has_developer_mode,
            has_insert_columns=has_insert_columns,
            has_auto_open=has_auto_open,
        )

        logger.info(
            "scan_complete",
            template=capability.name,
            sheets=len(sheets),
            macros=len(macros),
            methodology=methodology,
            dimensions=dimension_count,
        )
        return capability

    except ImportError:
        logger.warning("win32com_not_available", msg="Falling back to metadata-only scan")
        return _scan_metadata_only(file_path, file_hash)
    except Exception as e:
        logger.error("scan_failed", error=str(e))
        # Attempt COM cleanup
        try:
            pythoncom.CoUninitialize()  # type: ignore
        except Exception:
            pass
        raise ExcelError(f"Workbook scan failed: {e}") from e


def _scan_metadata_only(file_path: Path, file_hash: str) -> TemplateCapability:
    """Fallback scan using only filename heuristics (no COM)."""
    fname_lower = file_path.stem.lower()

    methodology = ""
    if "vlookup" in fname_lower:
        methodology = "VLOOKUP"
    elif "pivot" in fname_lower:
        methodology = "PIVOT"
    elif "ref" in fname_lower:
        methodology = "REF"

    dimension_count = 1
    if "2 dim" in fname_lower or "2_dim" in fname_lower:
        dimension_count = 2

    template_type = "master"
    if "comparison" in fname_lower:
        template_type = "comparison"
    elif "ranking" in fname_lower:
        template_type = "ranking"
    elif "share" in fname_lower:
        template_type = "share"
    elif "trended" in fname_lower:
        template_type = "trended"
    elif "top item" in fname_lower:
        template_type = "top_item"

    return TemplateCapability(
        name=file_path.stem,
        file_hash=file_hash,
        file_path=str(file_path),
        status=TemplateStatus.CANDIDATE,
        methodology=methodology,
        dimension_count=dimension_count,
    )
