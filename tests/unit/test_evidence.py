"""Tests for the V2 ExecutionEvidence and ExecutionTrace models."""

import pytest
from eap.core.contracts.models import (
    ExecutionEvidence,
    ExecutionTrace,
    VerificationStatus,
    ImplementationStatus,
    RunState,
)


class TestExecutionEvidence:
    """Test ExecutionEvidence model per V1 review §18.2."""

    def test_evidence_has_five_mandatory_fields(self):
        """Intent → Action → Observation → Verification → Evidence."""
        ev = ExecutionEvidence(
            intent="Select Total ALDI market",
            action="Clicked market selector and chose Total ALDI",
            observation="UI shows Total ALDI in the selected markets panel",
            verification="DOM inspection confirms selected-item[text='Total ALDI']",
            evidence="screenshot_path: /artifacts/markets_selected.png",
        )
        assert ev.intent != ""
        assert ev.action != ""
        assert ev.observation != ""
        assert ev.verification != ""
        assert ev.evidence != ""

    def test_evidence_default_status_is_unverified(self):
        ev = ExecutionEvidence()
        assert ev.status == VerificationStatus.UNVERIFIED

    def test_evidence_has_step_id(self):
        ev = ExecutionEvidence()
        assert ev.step_id != ""

    def test_evidence_tracks_cost_and_latency(self):
        ev = ExecutionEvidence(latency_ms=150.5, token_cost=0.03, model_name="gpt-4o")
        assert ev.latency_ms == 150.5
        assert ev.token_cost == 0.03
        assert ev.model_name == "gpt-4o"

    def test_evidence_tracks_requested_vs_selected(self):
        ev = ExecutionEvidence(
            requested_value="Latest month",
            selected_value="Current Scan Periods",
        )
        assert ev.requested_value == "Latest month"
        assert ev.selected_value == "Current Scan Periods"


class TestExecutionTrace:
    """Test ExecutionTrace model per V1 review §28."""

    def test_trace_collects_steps(self):
        trace = ExecutionTrace(run_id="run-1", request_id="req-1")
        trace.steps.append(ExecutionEvidence(intent="step 1"))
        trace.steps.append(ExecutionEvidence(intent="step 2"))
        assert len(trace.steps) == 2

    def test_trace_default_status_is_unverified(self):
        trace = ExecutionTrace()
        assert trace.final_status == "UNVERIFIED"


class TestVerificationStatus:
    """Test VerificationStatus enum per V1 review §17."""

    def test_all_required_statuses_exist(self):
        assert VerificationStatus.UNVERIFIED
        assert VerificationStatus.VERIFIED
        assert VerificationStatus.FAILED
        assert VerificationStatus.NOT_IMPLEMENTED
        assert VerificationStatus.REQUIRES_HUMAN
        assert VerificationStatus.BLOCKED


class TestImplementationStatus:
    """Test honest reporting statuses per V1 review §42."""

    def test_all_required_statuses_exist(self):
        assert ImplementationStatus.IMPLEMENTED
        assert ImplementationStatus.VERIFIED
        assert ImplementationStatus.PARTIALLY_IMPLEMENTED
        assert ImplementationStatus.BLOCKED
        assert ImplementationStatus.NOT_IMPLEMENTED
        assert ImplementationStatus.FAILED
        assert ImplementationStatus.REQUIRES_HUMAN
        assert ImplementationStatus.UNVERIFIED


class TestRunStateEvidenceTrail:
    """Test that RunState carries an evidence trail."""

    def test_run_state_has_evidence_trail(self):
        state = RunState()
        assert hasattr(state, "evidence_trail")
        assert state.evidence_trail == []

    def test_evidence_appends_to_trail(self):
        state = RunState()
        state.evidence_trail.append(ExecutionEvidence(intent="test"))
        assert len(state.evidence_trail) == 1
