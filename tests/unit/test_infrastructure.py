"""Tests for errors, events, config, spec parser, template registry."""

import pytest
from pathlib import Path

from eap.core.errors.exceptions import (
    EAPError,
    AuthenticationError,
    DiscoverUIError,
    SemanticError,
    AmbiguousResolutionError,
    ExcelError,
    MacroError,
    QCError,
    FormulaError,
    StructureError,
)
from eap.core.contracts.models import ErrorCode
from eap.core.events.models import RunEvent, EventType
from eap.core.config import EAPSettings, generate_run_id
from eap.ingestion.template_discovery.registry import TemplateRegistry
from eap.core.contracts.models import TemplateCapability, TemplateStatus


class TestErrorHierarchy:
    def test_base_error(self):
        err = EAPError("something broke")
        assert err.code == ErrorCode.SYSTEM
        assert str(err) == "something broke"

    def test_auth_error(self):
        err = AuthenticationError("session expired")
        assert err.code == ErrorCode.AUTH
        assert not err.retryable

    def test_discover_ui_error_retryable(self):
        err = DiscoverUIError("button not found")
        assert err.code == ErrorCode.DISCOVER_UI
        assert err.retryable

    def test_semantic_error(self):
        err = AmbiguousResolutionError("multiple matches")
        assert err.code == ErrorCode.RESOLUTION
        assert not err.retryable

    def test_excel_error(self):
        err = ExcelError("COM failed")
        assert err.code == ErrorCode.EXCEL

    def test_macro_error(self):
        err = MacroError("InsertColumns timeout")
        assert err.code == ErrorCode.MACRO
        assert err.retryable

    def test_formula_error(self):
        err = FormulaError("#REF! in cell B5")
        assert err.code == ErrorCode.FORMULA

    def test_structure_error(self):
        err = StructureError("Output sheet missing")
        assert err.code == ErrorCode.STRUCTURE

    def test_error_with_details(self):
        err = EAPError(
            "detailed error",
            code=ErrorCode.DATA,
            details={"expected_rows": 100, "actual_rows": 0},
        )
        assert err.details["expected_rows"] == 100


class TestEvents:
    def test_event_creation(self):
        event = RunEvent(
            event_type=EventType.NODE_STARTED,
            run_id="run_123",
            node_id="configure_facts",
        )
        assert event.event_type == EventType.NODE_STARTED
        assert event.run_id == "run_123"
        assert event.timestamp is not None

    def test_event_with_metadata(self):
        event = RunEvent(
            event_type=EventType.MACRO_EXECUTED,
            run_id="run_123",
            node_id="run_macros",
            metadata={"macro_name": "InsertColumns", "duration_ms": 1500},
        )
        assert event.metadata["macro_name"] == "InsertColumns"


class TestConfig:
    def test_default_settings(self):
        s = EAPSettings()
        assert s.app_name == "EAP"
        assert s.confidence_high == 0.95
        assert s.confidence_medium == 0.80
        assert s.confidence_low == 0.60
        assert s.max_retries == 3
        assert s.nie_marker_filename == "NIE.txt"

    def test_run_id_generation(self):
        id1 = generate_run_id()
        id2 = generate_run_id()
        assert id1 != id2
        assert len(id1) == 36  # UUID format


class TestTemplateRegistry:
    def setup_method(self):
        self.registry = TemplateRegistry()

    def test_register_and_get(self):
        t = TemplateCapability(name="Test Template", file_hash="abc123")
        tid = self.registry.register(t)
        retrieved = self.registry.get(tid)
        assert retrieved is not None
        assert retrieved.name == "Test Template"

    def test_deduplication_by_hash(self):
        t1 = TemplateCapability(name="Template 1", file_hash="same_hash")
        t2 = TemplateCapability(name="Template 2", file_hash="same_hash")
        tid1 = self.registry.register(t1)
        tid2 = self.registry.register(t2)
        assert tid1 == tid2  # Same hash → same template

    def test_get_by_name(self):
        self.registry.register(TemplateCapability(
            name="01_Excel Best-fit_Master Template - 1 Dimension",
            file_hash="h1",
        ))
        result = self.registry.get_by_name("Master Template")
        assert result is not None

    def test_activate(self):
        t = TemplateCapability(name="Test", file_hash="h2")
        tid = self.registry.register(t)
        self.registry.activate(tid)
        retrieved = self.registry.get(tid)
        assert retrieved.status == TemplateStatus.ACTIVATED

    def test_find_best_match(self):
        t = TemplateCapability(
            name="VLOOKUP 1D",
            file_hash="h3",
            methodology="VLOOKUP",
            dimension_count=1,
        )
        tid = self.registry.register(t)
        self.registry.activate(tid)

        match = self.registry.find_best_match(
            methodology="VLOOKUP",
            dimension_count=1,
        )
        assert match is not None
        assert match.name == "VLOOKUP 1D"

    def test_list_activated(self):
        t1 = TemplateCapability(name="T1", file_hash="h4")
        t2 = TemplateCapability(name="T2", file_hash="h5")
        tid1 = self.registry.register(t1)
        self.registry.register(t2)
        self.registry.activate(tid1)

        activated = self.registry.list_activated()
        assert len(activated) == 1
