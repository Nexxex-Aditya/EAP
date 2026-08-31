"""Custom exception hierarchy for the EAP platform.

Every error maps to the taxonomy defined in rules.md §11 and V1 review §27.

Per V1 review §27, every error should have:
error_code, category, severity, component, operation, context,
root_cause, recoverable, recovery_attempts, evidence, final_status.
"""

from __future__ import annotations

from typing import Any

from eap.core.contracts.models import ErrorCode


class EAPError(Exception):
    """Base exception for all EAP errors.

    Enriched per V1 review §27 with severity, component, operation,
    root_cause, recovery_attempts, evidence, and final_status.
    """

    code: ErrorCode = ErrorCode.SYSTEM
    message: str = ""
    retryable: bool = False
    details: dict | None = None

    # V1 review §27 additions
    severity: str = "error"       # error | warning | info
    component: str = ""           # e.g., "discover", "excel", "resolver"
    operation: str = ""           # e.g., "select_facts", "run_macro"
    root_cause: str = ""
    recovery_attempts: int = 0
    evidence: str = ""
    final_status: str = "FAILED"  # FAILED | RECOVERED | ESCALATED

    def __init__(
        self,
        message: str = "",
        *,
        code: ErrorCode | None = None,
        retryable: bool | None = None,
        details: dict | None = None,
        severity: str | None = None,
        component: str | None = None,
        operation: str | None = None,
        root_cause: str | None = None,
        evidence: str | None = None,
    ) -> None:
        self.message = message or self.__class__.__doc__ or ""
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.details = details or {}
        if severity is not None:
            self.severity = severity
        if component is not None:
            self.component = component
        if operation is not None:
            self.operation = operation
        if root_cause is not None:
            self.root_cause = root_cause
        if evidence is not None:
            self.evidence = evidence
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for logging and observability."""
        return {
            "error_code": self.code.value,
            "category": self.code.value,
            "severity": self.severity,
            "component": self.component,
            "operation": self.operation,
            "message": self.message,
            "root_cause": self.root_cause,
            "recoverable": self.retryable,
            "recovery_attempts": self.recovery_attempts,
            "evidence": self.evidence,
            "final_status": self.final_status,
            "details": self.details,
        }


# --- Authentication ---

class AuthenticationError(EAPError):
    """Authentication failed or session expired."""
    code = ErrorCode.AUTH
    retryable = False
    component = "auth"


class AuthorizationError(EAPError):
    """Insufficient permissions for the requested operation."""
    code = ErrorCode.AUTHORIZATION
    retryable = False
    component = "auth"


# --- Browser ---

class BrowserError(EAPError):
    """Browser automation operation failed."""
    code = ErrorCode.BROWSER
    retryable = True
    component = "browser"


# --- Discover ---

class DiscoverError(EAPError):
    """Discover service operation failed."""
    code = ErrorCode.DISCOVER
    retryable = True
    component = "discover"


class DiscoverUIError(EAPError):
    """NielsenIQ Discover UI mismatch or unexpected state."""
    code = ErrorCode.DISCOVER_UI
    retryable = True
    component = "discover"


class DiscoverUIElementNotFound(DiscoverUIError):
    """Expected UI element was not found in Discover."""
    retryable = True


class DiscoverUIDrift(DiscoverUIError):
    """Discover UI has changed from the expected layout."""
    retryable = True


# --- Semantic / Resolution ---

class SemanticError(EAPError):
    """Business term could not be resolved with sufficient confidence."""
    code = ErrorCode.SEMANTIC
    retryable = False
    component = "resolver"


class AmbiguousResolutionError(SemanticError):
    """Multiple candidate interpretations exist — human approval required."""
    code = ErrorCode.RESOLUTION


class UnresolvableTermError(SemanticError):
    """Business term has no candidate interpretation (confidence < 0.60)."""
    code = ErrorCode.RESOLUTION


# --- Data ---

class DataError(EAPError):
    """Unexpected data returned from Discover or workbook."""
    code = ErrorCode.DATA
    retryable = False
    component = "data"


class EmptyDataError(DataError):
    """Query returned no data."""


class DataDimensionMismatch(DataError):
    """Returned data dimensions do not match the expected plan."""


# --- Excel ---

class ExcelError(EAPError):
    """Excel workbook operation failed."""
    code = ErrorCode.EXCEL
    retryable = False
    component = "excel"


class WorkbookOpenError(ExcelError):
    """Failed to open the workbook."""


class WorkbookSaveError(ExcelError):
    """Failed to save the workbook."""


class WorkbookProtectedError(ExcelError):
    """Workbook is in a protected/locked state that prevents operation."""


# --- Macro ---

class MacroError(EAPError):
    """Macro execution failed."""
    code = ErrorCode.MACRO
    retryable = True
    component = "excel"


class MacroNotFoundError(MacroError):
    """Specified macro does not exist in the workbook."""
    retryable = False


class MacroVerificationError(MacroError):
    """Macro ran but its expected effect was not verified."""
    retryable = True


# --- Formula ---

class FormulaError(EAPError):
    """Formula defect detected in the workbook."""
    code = ErrorCode.FORMULA
    retryable = False
    component = "excel"


class BrokenFormulaError(FormulaError):
    """Formula references are broken or produce errors."""


# --- Structure ---

class StructureError(EAPError):
    """Workbook structure defect detected."""
    code = ErrorCode.STRUCTURE
    retryable = False
    component = "excel"


class MissingSheetError(StructureError):
    """Expected worksheet is missing."""


class MissingRangeError(StructureError):
    """Expected named range is missing."""


# --- QC ---

class QCError(EAPError):
    """Quality control validation failed."""
    code = ErrorCode.QC
    retryable = False
    component = "qc"


class QCNotPassedError(QCError):
    """One or more QC checks failed."""


# --- Model / LLM ---

class ModelError(EAPError):
    """LLM/model operation failed."""
    code = ErrorCode.MODEL
    retryable = True
    component = "model"


class ModelUnavailableError(ModelError):
    """Requested model is not available or health check failed."""


# --- Tool ---

class ToolError(EAPError):
    """Tool invocation failed."""
    code = ErrorCode.TOOL
    retryable = True
    component = "tool"


class ToolPermissionDenied(ToolError):
    """Tool invocation denied by policy engine."""
    retryable = False


# --- Timeout ---

class TimeoutError(EAPError):
    """Operation exceeded its time limit."""
    code = ErrorCode.TIMEOUT
    retryable = True


# --- Validation ---

class ValidationError(EAPError):
    """Input or state validation failed."""
    code = ErrorCode.VALIDATION
    retryable = False
    component = "validation"


# --- Memory ---

class MemoryError(EAPError):
    """Memory system operation failed."""
    code = ErrorCode.MEMORY
    retryable = False
    component = "memory"


class MemoryPromotionError(MemoryError):
    """Memory promotion rule violation."""


# --- System ---

class SystemError(EAPError):
    """Infrastructure or system-level failure."""
    code = ErrorCode.SYSTEM
    retryable = True
    component = "system"


class WorkspaceError(SystemError):
    """Workspace preparation or validation failed."""


class ConfigurationError(SystemError):
    """System configuration is missing or invalid."""
    retryable = False
