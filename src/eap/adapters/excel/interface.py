"""Abstract Excel adapter interface.

Per architecture.md §8, all Excel COM operations go through this interface.
The Windows COM implementation (pywin32) lives in a separate module.
Domain code never imports pywin32 directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ExcelAdapter(ABC):
    """Abstract interface for Excel workbook operations."""

    @abstractmethod
    def open(self, file_path: str | Path, *, read_only: bool = False) -> None:
        """Open an Excel workbook."""

    @abstractmethod
    def create_working_copy(self, source: str | Path, destination: str | Path) -> str:
        """Create a versioned working copy of a template. Returns destination path."""

    @abstractmethod
    def inspect(self) -> dict[str, Any]:
        """Inspect the currently open workbook: sheets, names, macros, etc."""

    @abstractmethod
    def read_range(self, sheet: str, range_address: str) -> list[list[Any]]:
        """Read values from a range. Returns 2D list."""

    @abstractmethod
    def write_range(self, sheet: str, range_address: str, values: list[list[Any]]) -> None:
        """Write values to a range."""

    @abstractmethod
    def get_sheets(self) -> list[dict[str, Any]]:
        """List all sheets with visibility and basic metadata."""

    @abstractmethod
    def get_named_ranges(self) -> list[dict[str, str]]:
        """List all named ranges with their addresses."""

    @abstractmethod
    def get_macros(self) -> list[str]:
        """List available macro names in the workbook."""

    @abstractmethod
    def run_macro(self, macro_name: str, *args: Any) -> Any:
        """Execute a macro by name. Returns macro result if any."""

    @abstractmethod
    def get_formulas(self, sheet: str, range_address: str) -> list[list[str]]:
        """Read formula strings from a range."""

    @abstractmethod
    def detect_formula_errors(self, sheet: str) -> list[dict[str, Any]]:
        """Scan a sheet for formula errors (#REF!, #VALUE!, #NAME?, etc.)."""

    @abstractmethod
    def set_sheet_visibility(self, sheet: str, visible: bool) -> None:
        """Show or hide a worksheet."""

    @abstractmethod
    def validate(self) -> dict[str, Any]:
        """Run structural validation on the workbook."""

    @abstractmethod
    def save(self, path: str | Path | None = None) -> str:
        """Save the workbook. Returns the saved file path."""

    @abstractmethod
    def close(self) -> None:
        """Close the workbook and release COM resources."""
