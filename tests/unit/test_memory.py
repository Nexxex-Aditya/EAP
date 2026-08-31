"""Tests for the memory system."""

import pytest
from eap.memory.system import (
    MemorySystem,
    MemoryStore,
    EpisodicEntry,
    SemanticEntry,
    ProceduralEntry,
    FailureEntry,
)
from eap.core.contracts.models import MemoryPromotionStatus


class TestMemoryStore:
    def setup_method(self):
        self.store = MemoryStore("test")

    def test_add_and_get(self):
        entry = EpisodicEntry(run_id="run_1", outcome="success")
        entry_id = self.store.add(entry)
        retrieved = self.store.get(entry_id)
        assert retrieved is not None
        assert retrieved.entry_id == entry_id

    def test_list_all(self):
        self.store.add(EpisodicEntry(run_id="r1"))
        self.store.add(EpisodicEntry(run_id="r2"))
        assert len(self.store.list_all()) == 2

    def test_list_by_status(self):
        e1 = EpisodicEntry(run_id="r1")
        e2 = EpisodicEntry(run_id="r2")
        self.store.add(e1)
        eid2 = self.store.add(e2)
        self.store.promote(eid2, MemoryPromotionStatus.CANDIDATE)
        
        observed = self.store.list_all(status=MemoryPromotionStatus.OBSERVED)
        candidates = self.store.list_all(status=MemoryPromotionStatus.CANDIDATE)
        assert len(observed) == 1
        assert len(candidates) == 1

    def test_promotion_valid_sequence(self):
        entry = SemanticEntry(canonical_name="Sales Value")
        eid = self.store.add(entry)

        # Valid promotion sequence
        assert self.store.promote(eid, MemoryPromotionStatus.CANDIDATE)
        assert self.store.promote(eid, MemoryPromotionStatus.REPRODUCED)
        assert self.store.promote(eid, MemoryPromotionStatus.TESTED)
        assert self.store.promote(eid, MemoryPromotionStatus.VALIDATED)
        assert self.store.promote(eid, MemoryPromotionStatus.APPROVED)
        assert self.store.promote(eid, MemoryPromotionStatus.PROMOTED)

        retrieved = self.store.get(eid)
        assert retrieved.promotion_status == MemoryPromotionStatus.PROMOTED

    def test_promotion_invalid_skip(self):
        entry = SemanticEntry(canonical_name="Sales Value")
        eid = self.store.add(entry)

        # Cannot skip from OBSERVED to TESTED
        assert not self.store.promote(eid, MemoryPromotionStatus.TESTED)

    def test_rollback(self):
        entry = SemanticEntry(canonical_name="test")
        eid = self.store.add(entry)
        self.store.promote(eid, MemoryPromotionStatus.CANDIDATE)
        
        assert self.store.rollback(eid)
        retrieved = self.store.get(eid)
        assert retrieved.promotion_status == MemoryPromotionStatus.ROLLED_BACK

    def test_search(self):
        self.store.add(SemanticEntry(canonical_name="Sales Value"))
        self.store.add(SemanticEntry(canonical_name="Sales Units"))

        results = self.store.search("Sales Value")
        assert len(results) >= 1


class TestMemorySystem:
    def test_initialization(self):
        mem = MemorySystem()
        assert mem.episodic is not None
        assert mem.semantic is not None
        assert mem.procedural is not None
        assert mem.failure is not None
        assert mem.client_policy is not None
        assert mem.template is not None

    def test_record_run(self):
        mem = MemorySystem()
        eid = mem.record_run(EpisodicEntry(
            run_id="test_run",
            outcome="success",
            duration_seconds=45.0,
        ))
        assert eid != ""

    def test_record_failure(self):
        mem = MemorySystem()
        fid = mem.record_failure(FailureEntry(
            failure_signature="MACRO:InsertColumns:timeout",
            error_code="MACRO",
            resolution="Increased timeout to 30s",
        ))
        assert fid != ""

    def test_promoted_aliases(self):
        mem = MemorySystem()
        entry = SemanticEntry(canonical_name="Sales Value", aliases=["SV", "revenue"])
        eid = mem.record_alias(entry)
        
        # Not promoted yet
        assert len(mem.get_promoted_aliases()) == 0
