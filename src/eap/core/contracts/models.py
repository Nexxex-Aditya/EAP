"""Core domain contracts for the EAP platform.

All Pydantic models used across the system are defined here.
Domain code depends on these contracts; external adapters implement them.
No vendor SDK imports are allowed in this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class RunStatus(str, Enum):
    """Lifecycle states of a report run."""
    PLANNED = "planned"
    RUNNING = "running"
    WAITING = "waiting"
    RECOVERED = "recovered"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ConfidenceLevel(str, Enum):
    """Confidence routing buckets per rules.md §5."""
    HIGH = "high"          # >= 0.95 — may proceed if verified
    MEDIUM = "medium"      # 0.80–0.95 — proceed with validated policy
    LOW = "low"            # 0.60–0.80 — candidate only, human required
    UNRESOLVABLE = "unresolvable"  # < 0.60 — stop


class ErrorCode(str, Enum):
    """Error taxonomy per rules.md §11 and V1 review §27."""
    AUTH = "AUTH"
    AUTHORIZATION = "AUTHORIZATION"
    BROWSER = "BROWSER"
    DISCOVER = "DISCOVER"
    DISCOVER_UI = "DISCOVER_UI"
    RESOLUTION = "RESOLUTION"
    SEMANTIC = "SEMANTIC"
    DATA = "DATA"
    EXCEL = "EXCEL"
    MACRO = "MACRO"
    FORMULA = "FORMULA"
    STRUCTURE = "STRUCTURE"
    QC = "QC"
    MEMORY = "MEMORY"
    MODEL = "MODEL"
    TOOL = "TOOL"
    TIMEOUT = "TIMEOUT"
    VALIDATION = "VALIDATION"
    SYSTEM = "SYSTEM"


class VerificationStatus(str, Enum):
    """Status of an independent verification step (V1 review §17)."""
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"
    BLOCKED = "BLOCKED"


class ImplementationStatus(str, Enum):
    """Honest reporting status per V1 review §42."""
    IMPLEMENTED = "IMPLEMENTED"
    VERIFIED = "VERIFIED"
    PARTIALLY_IMPLEMENTED = "PARTIALLY_IMPLEMENTED"
    BLOCKED = "BLOCKED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    FAILED = "FAILED"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"
    UNVERIFIED = "UNVERIFIED"


class QCCategory(str, Enum):
    """QC check categories."""
    NUMERICAL = "numerical"
    FORMULA = "formula"
    STRUCTURAL = "structural"
    TEXTUAL = "textual"
    VISUAL = "visual"
    INTEGRITY = "integrity"
    NAMING = "naming"


class FormatStyle(str, Enum):
    """Discover table format styles."""
    LIST = "list"
    GROUP = "group"
    TREE = "tree"


class DimensionPlacement(str, Enum):
    """Where a dimension is placed in the Discover query."""
    ROWS = "rows"
    COLUMNS = "columns"
    PAGE_BAR = "page_bar"


class TemplateStatus(str, Enum):
    """Template activation lifecycle."""
    CANDIDATE = "candidate"
    PENDING_REVIEW = "pending_review"
    ACTIVATED = "activated"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class MemoryPromotionStatus(str, Enum):
    """Self-healing promotion pipeline per memory.md §6."""
    OBSERVED = "observed"
    CANDIDATE = "candidate"
    REPRODUCED = "reproduced"
    TESTED = "tested"
    VALIDATED = "validated"
    APPROVED = "approved"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------

class DimensionSelection(BaseModel):
    """A selected dimension value (fact, product, market, or period)."""
    name: str
    values: list[str] = Field(default_factory=list)
    hierarchy_path: list[str] = Field(
        default_factory=list,
        description="Path through the hierarchy to reach the selected values",
    )
    select_all: bool = False
    select_all_except: list[str] = Field(default_factory=list)


class LayoutConfig(BaseModel):
    """How dimensions are arranged in the Discover query."""
    rows: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    page_bar: list[str] = Field(default_factory=list)


class FormatConfig(BaseModel):
    """Discover table format configuration."""
    style: FormatStyle = FormatStyle.LIST
    concatenate_characteristics: bool = False
    show_short_description: bool = False
    include_null_values: bool = False


class MacroSpec(BaseModel):
    """Specification for a macro that a template requires."""
    name: str
    description: str = ""
    run_order: int = 0
    precondition: str = ""
    expected_effect: str = ""
    is_required: bool = True


class SheetInfo(BaseModel):
    """Metadata about a worksheet within a workbook."""
    name: str
    index: int
    visible: bool = True
    has_formulas: bool = False
    formula_count: int = 0
    named_ranges: list[str] = Field(default_factory=list)
    row_count: int = 0
    col_count: int = 0
    is_output_sheet: bool = False


# ---------------------------------------------------------------------------
# Core Domain Models
# ---------------------------------------------------------------------------

class ReportRequest(BaseModel):
    """Incoming request for a report — the entry point to the pipeline.

    Can be constructed from natural language or explicit structured parameters.
    """
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Who / what
    client: str = ""
    user: str = ""
    description: str = ""
    natural_language_input: str = ""

    # Explicit parameters (override NL when provided)
    dataset_hint: str = ""
    view_hint: str = ""
    template_hint: str = ""
    region: str = ""

    # Dimension requests (may use business language, not Discover labels)
    facts: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)
    periods: list[str] = Field(default_factory=list)

    # Format/layout
    format_config: FormatConfig | None = None
    layout_config: LayoutConfig | None = None

    # Output
    output_name: str = ""
    output_path: str = ""

    # Policy
    approval_policy: str = "default"


class ResolutionResult(BaseModel):
    """Result of resolving a single business term against Discover choices.

    Per V1 review §7, every resolved entity must contain:
    requested value, actual selected value, entity type, confidence,
    resolution method, evidence, alternatives considered, verification status.
    """
    requested: str
    resolved: str = ""
    entity_type: str = ""  # fact, product, market, period, dataset, view
    confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNRESOLVABLE
    method: str = ""  # exact, alias, synonym, hierarchy, context, etc.
    alternatives: list[str] = Field(default_factory=list)
    alternatives_considered: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Each alternative with its score and rejection reason",
    )
    requires_approval: bool = False
    evidence: str = ""
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED


class DiscoverPlan(BaseModel):
    """Fully resolved plan for a Discover query, ready for execution."""
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = ""

    region: str = ""
    offering: str = ""
    dataset: ResolutionResult | None = None
    view: ResolutionResult | None = None

    facts: list[ResolutionResult] = Field(default_factory=list)
    products: list[DimensionSelection] = Field(default_factory=list)
    markets: list[DimensionSelection] = Field(default_factory=list)
    periods: list[DimensionSelection] = Field(default_factory=list)

    format_config: FormatConfig = Field(default_factory=FormatConfig)
    layout_config: LayoutConfig = Field(default_factory=LayoutConfig)

    start_cell: str = "A1"
    range_name: str = ""

    requires_approval: bool = False
    unresolved_items: list[ResolutionResult] = Field(default_factory=list)


class DiscoverResult(BaseModel):
    """Outcome of executing a Discover query."""
    plan_id: str = ""
    success: bool = False
    row_count: int = 0
    col_count: int = 0
    range_address: str = ""
    screenshots: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    verification_passed: bool = False


class TemplateCapability(BaseModel):
    """Capability profile extracted from a workbook template.

    This is the central metadata that drives capability-driven orchestration
    (architecture.md §15) — no hard-coded template branches.
    """
    template_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    version: str = "1.0.0"
    file_hash: str = ""
    file_path: str = ""
    status: TemplateStatus = TemplateStatus.CANDIDATE

    # Methodology
    methodology: str = ""  # e.g., "VLOOKUP", "PIVOT", "REF"
    dimension_count: int = 1

    # Dimensions
    supported_row_dimensions: list[str] = Field(default_factory=list)
    supported_col_dimensions: list[str] = Field(default_factory=list)
    supported_page_dimensions: list[str] = Field(default_factory=list)
    default_layout: LayoutConfig | None = None

    # Sheets
    sheets: list[SheetInfo] = Field(default_factory=list)
    output_sheets: list[str] = Field(default_factory=list)
    hidden_sheets: list[str] = Field(default_factory=list)

    # Macros
    macros: list[MacroSpec] = Field(default_factory=list)
    has_developer_mode: bool = False
    has_insert_columns: bool = False
    has_auto_open: bool = False

    # Output
    output_start_cell: str = "A1"
    max_data_rows: int = 500

    # QC
    qc_profile: str = "default"

    # Specification
    specification_id: str = ""


class ReportPlan(BaseModel):
    """Complete execution plan joining request, template, and Discover plan."""
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = ""
    template_id: str = ""
    discover_plan_id: str = ""

    request: ReportRequest | None = None
    template: TemplateCapability | None = None
    discover_plan: DiscoverPlan | None = None

    workspace_path: str = ""
    working_copy_path: str = ""

    macro_sequence: list[str] = Field(default_factory=list)
    qc_profile: str = "default"

    approved: bool = False
    approved_by: str = ""
    approved_at: datetime | None = None


class WorkbookResult(BaseModel):
    """Outcome of Excel workbook operations."""
    success: bool = False
    file_path: str = ""
    sheets_processed: list[str] = Field(default_factory=list)
    macros_executed: list[str] = Field(default_factory=list)
    formulas_repaired: int = 0
    structures_repaired: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QCCheckResult(BaseModel):
    """Result of a single QC check."""
    check_id: str = ""
    category: QCCategory = QCCategory.NUMERICAL
    name: str = ""
    passed: bool = False
    message: str = ""
    evidence: str = ""
    severity: str = "error"  # error | warning | info
    repairable: bool = False


class QCResult(BaseModel):
    """Aggregate QC result for a report run."""
    run_id: str = ""
    checks: list[QCCheckResult] = Field(default_factory=list)
    passed: bool = False
    total_checks: int = 0
    passed_count: int = 0
    failed_count: int = 0
    warning_count: int = 0

    def compute_summary(self) -> None:
        """Recompute summary fields from individual checks."""
        self.total_checks = len(self.checks)
        self.passed_count = sum(1 for c in self.checks if c.passed)
        self.failed_count = sum(
            1 for c in self.checks if not c.passed and c.severity == "error"
        )
        self.warning_count = sum(
            1 for c in self.checks if not c.passed and c.severity == "warning"
        )
        self.passed = self.failed_count == 0


class RunState(BaseModel):
    """Mutable state for a single report execution run."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = ""
    plan_id: str = ""
    status: RunStatus = RunStatus.PLANNED

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    current_node: str = ""
    node_history: list[dict[str, Any]] = Field(default_factory=list)

    workspace_path: str = ""
    template_hash: str = ""
    working_copy_hash: str = ""

    discover_result: DiscoverResult | None = None
    workbook_result: WorkbookResult | None = None
    qc_result: QCResult | None = None

    errors: list[dict[str, Any]] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)

    retry_count: int = 0
    max_retries: int = 3

    # Execution evidence trail (V1 review §18.2)
    evidence_trail: list["ExecutionEvidence"] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Specification Models
# ---------------------------------------------------------------------------

class SpecificationRequirement(BaseModel):
    """A single requirement extracted from a specification document."""
    dimension: str = ""  # facts, products, markets, periods, format, layout, macro, qc
    requirement: str = ""
    constraint: str = ""  # e.g., "no limitation", "max 100", "mandatory order"
    notes: str = ""


class SpecificationProfile(BaseModel):
    """Structured profile extracted from a specification document."""
    spec_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    template_name: str = ""
    view_name: str = ""
    methodology: str = ""

    dimension_config: LayoutConfig | None = None
    requirements: list[SpecificationRequirement] = Field(default_factory=list)

    facts_notes: str = ""
    products_notes: str = ""
    markets_notes: str = ""
    periods_notes: str = ""

    macro_requirements: list[str] = Field(default_factory=list)
    output_sheet_notes: str = ""
    performance_notes: str = ""

    source_file: str = ""
    source_hash: str = ""


# ---------------------------------------------------------------------------
# Execution Evidence (V1 review §18.2, §28)
# ---------------------------------------------------------------------------

class ExecutionEvidence(BaseModel):
    """Evidence record for a single execution step.

    Per V1 review §18.2, every meaningful action needs:
    Intent → Action → Observation → Verification → Evidence.
    No evidence = no verified success.
    """
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    node_id: str = ""
    run_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # The 5 mandatory fields
    intent: str = ""          # What was the goal
    action: str = ""          # What was actually done
    observation: str = ""     # What was observed after
    verification: str = ""    # Independent verification result
    evidence: str = ""        # Proof (screenshot path, cell value, hash, etc.)

    # Metadata
    confidence: float = 0.0
    verifier: str = ""        # "deterministic" | "model" | "human"
    latency_ms: float = 0.0
    token_cost: float = 0.0
    model_name: str = ""
    status: VerificationStatus = VerificationStatus.UNVERIFIED

    # What was selected vs what was requested
    requested_value: str = ""
    selected_value: str = ""

    # Error/recovery if applicable
    error_code: str = ""
    recovery_action: str = ""


class ExecutionTrace(BaseModel):
    """Full observability trace for a run (V1 review §28).

    A developer must be able to answer:
    - Why did the system select this market?
    - Which model made this decision?
    - What did Discover actually show?
    - Why did QC pass?
    """
    run_id: str = ""
    request_id: str = ""
    workflow_id: str = ""
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    steps: list[ExecutionEvidence] = Field(default_factory=list)
    total_latency_ms: float = 0.0
    total_token_cost: float = 0.0
    final_status: str = "UNVERIFIED"
