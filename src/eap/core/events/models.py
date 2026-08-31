"""Structured event models emitted by every graph node.

Per architecture.md §14, every node emits: run_id, node_id, timestamp,
state_before, action, state_after, outcome, latency, retry_count,
model_metadata, artifact_references, error_code.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Categories of events emitted during execution."""
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_RETRYING = "node_retrying"
    NODE_SKIPPED = "node_skipped"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    STATE_TRANSITION = "state_transition"
    CHECKPOINT_CREATED = "checkpoint_created"
    MACRO_EXECUTED = "macro_executed"
    QC_CHECK_COMPLETED = "qc_check_completed"
    REPAIR_APPLIED = "repair_applied"
    MEMORY_CANDIDATE = "memory_candidate"
    SCREENSHOT_CAPTURED = "screenshot_captured"
    ERROR_OCCURRED = "error_occurred"


class RunEvent(BaseModel):
    """Immutable structured event emitted during a run.

    These events form the audit trail (prd.md F14).
    """
    event_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    event_type: EventType
    run_id: str
    node_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # State
    state_before: str = ""
    action: str = ""
    state_after: str = ""
    outcome: str = ""

    # Performance
    latency_ms: float = 0.0
    retry_count: int = 0

    # AI metadata (when an LLM call was involved)
    model_name: str = ""
    model_provider: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    # References
    artifact_paths: list[str] = Field(default_factory=list)
    screenshot_path: str = ""
    error_code: str = ""
    error_message: str = ""

    # Arbitrary structured payload
    metadata: dict[str, Any] = Field(default_factory=dict)
