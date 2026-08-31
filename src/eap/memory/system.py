"""Persistent memory system — stores and manages organizational knowledge.

Per memory.md §5, memory is split into:
  Episodic (runs, outcomes, evidence)
  Semantic (aliases, synonyms, language mappings)
  Procedural (workflows, recovery playbooks)
  Failure (signatures, fixes)
  Client Policy (terminology, preferences)
  Template (capabilities, versions)

Per memory.md §6, promotion follows:
  Observed → Candidate → Reproduced → Tested →
  Validated → Approved → Promoted → Monitored → Rollback if regression
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from eap.core.config import get_logger
from eap.core.contracts.models import MemoryPromotionStatus

logger = get_logger("memory")


# ---------------------------------------------------------------------------
# Memory Entry Models
# ---------------------------------------------------------------------------

class MemoryEntry(BaseModel):
    """Base model for all memory entries."""
    entry_id: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    source_run_id: str = ""
    promotion_status: MemoryPromotionStatus = MemoryPromotionStatus.OBSERVED
    tags: list[str] = Field(default_factory=list)


class EpisodicEntry(MemoryEntry):
    """A record of a past run."""
    run_id: str = ""
    request_summary: str = ""
    outcome: str = ""  # success, failure, partial
    duration_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list)
    template_used: str = ""
    evidence_paths: list[str] = Field(default_factory=list)


class SemanticEntry(MemoryEntry):
    """A validated semantic mapping."""
    canonical_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    language_mappings: dict[str, str] = Field(default_factory=dict)
    domain: str = ""  # facts, products, markets, periods


class ProceduralEntry(MemoryEntry):
    """An approved workflow or recovery strategy."""
    name: str = ""
    description: str = ""
    steps: list[str] = Field(default_factory=list)
    trigger_condition: str = ""
    success_count: int = 0
    failure_count: int = 0


class FailureEntry(MemoryEntry):
    """A recorded failure and its resolution."""
    failure_signature: str = ""
    error_code: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    resolution: str = ""
    resolution_verified: bool = False


class ClientPolicyEntry(MemoryEntry):
    """Client-specific terminology and preferences."""
    client: str = ""
    terminology: dict[str, str] = Field(default_factory=dict)
    period_policy: str = ""
    template_preferences: list[str] = Field(default_factory=list)
    approved_fallbacks: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Memory Stores
# ---------------------------------------------------------------------------

class MemoryStore:
    """In-memory store (production would use PostgreSQL).

    Provides CRUD operations and promotion lifecycle management.
    """

    def __init__(self, store_name: str) -> None:
        self.name = store_name
        self._entries: dict[str, MemoryEntry] = {}

    def add(self, entry: MemoryEntry) -> str:
        """Add an entry to the store."""
        if not entry.entry_id:
            entry.entry_id = f"{self.name}_{len(self._entries)}"
        self._entries[entry.entry_id] = entry
        logger.info("memory_added", store=self.name, entry_id=entry.entry_id)
        return entry.entry_id

    def get(self, entry_id: str) -> MemoryEntry | None:
        """Retrieve an entry by ID."""
        return self._entries.get(entry_id)

    def list_all(
        self,
        *,
        status: MemoryPromotionStatus | None = None,
    ) -> list[MemoryEntry]:
        """List entries, optionally filtered by promotion status."""
        entries = list(self._entries.values())
        if status is not None:
            entries = [e for e in entries if e.promotion_status == status]
        return entries

    def promote(self, entry_id: str, new_status: MemoryPromotionStatus) -> bool:
        """Advance an entry through the promotion pipeline.

        Per memory.md §6, never skip stages.
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            return False

        # Validate progression order
        valid_transitions: dict[MemoryPromotionStatus, MemoryPromotionStatus] = {
            MemoryPromotionStatus.OBSERVED: MemoryPromotionStatus.CANDIDATE,
            MemoryPromotionStatus.CANDIDATE: MemoryPromotionStatus.REPRODUCED,
            MemoryPromotionStatus.REPRODUCED: MemoryPromotionStatus.TESTED,
            MemoryPromotionStatus.TESTED: MemoryPromotionStatus.VALIDATED,
            MemoryPromotionStatus.VALIDATED: MemoryPromotionStatus.APPROVED,
            MemoryPromotionStatus.APPROVED: MemoryPromotionStatus.PROMOTED,
        }

        expected = valid_transitions.get(entry.promotion_status)
        if expected != new_status:
            logger.warning(
                "invalid_promotion",
                entry_id=entry_id,
                current=entry.promotion_status.value,
                requested=new_status.value,
            )
            return False

        entry.promotion_status = new_status
        entry.updated_at = datetime.utcnow()
        logger.info(
            "memory_promoted",
            store=self.name,
            entry_id=entry_id,
            new_status=new_status.value,
        )
        return True

    def rollback(self, entry_id: str) -> bool:
        """Rollback a promoted entry."""
        entry = self._entries.get(entry_id)
        if entry is None:
            return False
        entry.promotion_status = MemoryPromotionStatus.ROLLED_BACK
        entry.updated_at = datetime.utcnow()
        logger.info("memory_rolled_back", entry_id=entry_id)
        return True

    def search(self, query: str) -> list[MemoryEntry]:
        """Simple text search across entries."""
        query_lower = query.lower()
        return [
            e for e in self._entries.values()
            if query_lower in str(e.model_dump()).lower()
        ]


class MemorySystem:
    """Top-level memory system aggregating all memory stores."""

    def __init__(self) -> None:
        self.episodic = MemoryStore("episodic")
        self.semantic = MemoryStore("semantic")
        self.procedural = MemoryStore("procedural")
        self.failure = MemoryStore("failure")
        self.client_policy = MemoryStore("client_policy")
        self.template = MemoryStore("template")

    def record_run(self, entry: EpisodicEntry) -> str:
        """Record a completed run."""
        return self.episodic.add(entry)

    def record_alias(self, entry: SemanticEntry) -> str:
        """Record a semantic mapping."""
        return self.semantic.add(entry)

    def record_failure(self, entry: FailureEntry) -> str:
        """Record a failure for future learning."""
        return self.failure.add(entry)

    def record_procedure(self, entry: ProceduralEntry) -> str:
        """Record an approved procedure/playbook."""
        return self.procedural.add(entry)

    def get_promoted_aliases(self) -> list[MemoryEntry]:
        """Get all promoted semantic aliases."""
        return self.semantic.list_all(status=MemoryPromotionStatus.PROMOTED)

    def get_promoted_procedures(self) -> list[MemoryEntry]:
        """Get all promoted recovery procedures."""
        return self.procedural.list_all(status=MemoryPromotionStatus.PROMOTED)
