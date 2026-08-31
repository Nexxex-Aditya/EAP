"""Tests for core domain contracts."""

import pytest
from eap.core.contracts.models import (
    ConfidenceLevel,
    DimensionSelection,
    DiscoverPlan,
    DiscoverResult,
    ErrorCode,
    FormatConfig,
    FormatStyle,
    LayoutConfig,
    MacroSpec,
    MemoryPromotionStatus,
    QCCategory,
    QCCheckResult,
    QCResult,
    ReportPlan,
    ReportRequest,
    ResolutionResult,
    RunState,
    RunStatus,
    SheetInfo,
    SpecificationProfile,
    SpecificationRequirement,
    TemplateCapability,
    TemplateStatus,
    WorkbookResult,
)


class TestReportRequest:
    def test_default_creation(self):
        req = ReportRequest()
        assert req.request_id != ""
        assert req.created_at is not None
        assert req.facts == []
        assert req.approval_policy == "default"

    def test_with_parameters(self):
        req = ReportRequest(
            client="ALDI",
            dataset_hint="AU ALDI SCANTRACK",
            facts=["Sales Value", "Sales Units"],
            markets=["Total ALDI"],
            periods=["Latest 52 Weeks"],
            region="AU",
        )
        assert req.client == "ALDI"
        assert len(req.facts) == 2
        assert req.region == "AU"

    def test_natural_language_input(self):
        req = ReportRequest(
            natural_language_input="Prepare the ALDI SCANTRACK report for latest 52 weeks"
        )
        assert "ALDI" in req.natural_language_input


class TestResolutionResult:
    def test_exact_match(self):
        r = ResolutionResult(
            requested="Sales Value",
            resolved="Sales Value",
            confidence=1.0,
            confidence_level=ConfidenceLevel.HIGH,
            method="exact_match",
        )
        assert r.confidence == 1.0
        assert not r.requires_approval

    def test_unresolvable(self):
        r = ResolutionResult(
            requested="Unknown Fact",
            confidence=0.0,
            confidence_level=ConfidenceLevel.UNRESOLVABLE,
            requires_approval=True,
        )
        assert r.requires_approval
        assert r.resolved == ""


class TestTemplateCapability:
    def test_default(self):
        t = TemplateCapability()
        assert t.status == TemplateStatus.CANDIDATE
        assert t.dimension_count == 1
        assert not t.has_developer_mode

    def test_full_template(self):
        t = TemplateCapability(
            name="01_Excel Best-fit_Master Template - 1 Dimension",
            methodology="VLOOKUP",
            dimension_count=1,
            has_developer_mode=True,
            has_insert_columns=True,
            has_auto_open=True,
            macros=[
                MacroSpec(name="DeveloperMode", run_order=0),
                MacroSpec(name="InsertColumns", run_order=1),
                MacroSpec(name="auto_open", run_order=2),
            ],
            sheets=[
                SheetInfo(name="Welcome", index=0, visible=True),
                SheetInfo(name="Output", index=1, visible=True, is_output_sheet=True),
                SheetInfo(name="Data", index=2, visible=False),
            ],
            output_sheets=["Output"],
            hidden_sheets=["Data"],
        )
        assert t.methodology == "VLOOKUP"
        assert len(t.macros) == 3
        assert len(t.sheets) == 3
        assert t.has_developer_mode


class TestQCResult:
    def test_compute_summary_all_pass(self):
        qc = QCResult(
            checks=[
                QCCheckResult(name="check1", passed=True, category=QCCategory.NUMERICAL),
                QCCheckResult(name="check2", passed=True, category=QCCategory.FORMULA),
            ]
        )
        qc.compute_summary()
        assert qc.passed
        assert qc.total_checks == 2
        assert qc.passed_count == 2
        assert qc.failed_count == 0

    def test_compute_summary_with_failure(self):
        qc = QCResult(
            checks=[
                QCCheckResult(name="check1", passed=True, category=QCCategory.NUMERICAL),
                QCCheckResult(
                    name="check2", passed=False, category=QCCategory.FORMULA, severity="error"
                ),
            ]
        )
        qc.compute_summary()
        assert not qc.passed
        assert qc.failed_count == 1

    def test_warnings_dont_fail(self):
        qc = QCResult(
            checks=[
                QCCheckResult(name="check1", passed=True, category=QCCategory.NUMERICAL),
                QCCheckResult(
                    name="check2", passed=False, category=QCCategory.VISUAL, severity="warning"
                ),
            ]
        )
        qc.compute_summary()
        assert qc.passed  # Warnings don't cause failure
        assert qc.warning_count == 1


class TestRunState:
    def test_default(self):
        rs = RunState()
        assert rs.status == RunStatus.PLANNED
        assert rs.retry_count == 0
        assert rs.max_retries == 3

    def test_state_tracking(self):
        rs = RunState(
            current_node="configure_facts",
            status=RunStatus.RUNNING,
        )
        assert rs.current_node == "configure_facts"


class TestDiscoverPlan:
    def test_unresolved_items(self):
        plan = DiscoverPlan(
            region="AU",
            unresolved_items=[
                ResolutionResult(
                    requested="Unknown Period",
                    requires_approval=True,
                ),
            ],
        )
        assert plan.requires_approval is False  # Set explicitly
        assert len(plan.unresolved_items) == 1


class TestEnums:
    def test_error_codes(self):
        assert ErrorCode.AUTH.value == "AUTH"
        assert ErrorCode.DISCOVER_UI.value == "DISCOVER_UI"

    def test_run_status(self):
        assert RunStatus.PLANNED.value == "planned"
        assert RunStatus.COMPLETED.value == "completed"

    def test_confidence_levels(self):
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.UNRESOLVABLE.value == "unresolvable"

    def test_memory_promotion(self):
        assert MemoryPromotionStatus.OBSERVED.value == "observed"
        assert MemoryPromotionStatus.PROMOTED.value == "promoted"


class TestFormatConfig:
    def test_defaults(self):
        fc = FormatConfig()
        assert fc.style == FormatStyle.LIST
        assert not fc.concatenate_characteristics


class TestSpecificationProfile:
    def test_creation(self):
        sp = SpecificationProfile(
            template_name="01_Discover_Master Template - 1 Dimension",
            methodology="VLOOKUP",
            macro_requirements=["InsertColumns"],
        )
        assert sp.methodology == "VLOOKUP"
        assert "InsertColumns" in sp.macro_requirements
