"""Tests for the Skill base class per V1 review §19."""

import pytest
import asyncio
from typing import Any

from eap.skills.base import (
    Skill,
    SkillDefinition,
    SkillResult,
    SkillStatus,
)
from eap.core.governance.policy import PolicyEngine, GovernanceConfig
from eap.core.contracts.models import VerificationStatus


class PassingSkill(Skill):
    """A skill that executes and verifies successfully."""

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="test.passing",
            name="Passing Skill",
            description="Always succeeds",
            required_permissions=[],
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        return True, "OK"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"result": "done"}

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        return True, "Verified deterministically"


class FailingSkill(Skill):
    """A skill that fails during execution."""

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="test.failing",
            name="Failing Skill",
            description="Always fails",
            required_permissions=[],
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        return True, "OK"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Simulated execution failure")

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        return False, "Cannot verify"


class PreconditionFailSkill(Skill):
    """A skill whose preconditions are not met."""

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="test.precond_fail",
            name="Precondition Fail Skill",
            required_permissions=[],
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        return False, "Missing required input"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        return True, "OK"


class VerificationFailSkill(Skill):
    """A skill that executes but fails verification."""

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="test.verify_fail",
            name="Verification Fail Skill",
            required_permissions=[],
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        return True, "OK"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"result": "something"}

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        return False, "Output does not match expected structure"


class BlockedSkill(Skill):
    """A skill that requires a blocked permission."""

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            skill_id="test.blocked",
            name="Blocked Skill",
            required_permissions=["shell_execute"],
        )

    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        return True, "OK"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        return True, "OK"


def _run(coro):
    """Helper to run async in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestSkillLifecycle:
    """Test the full skill lifecycle per V1 review §19."""

    def test_passing_skill_returns_verified(self):
        skill = PassingSkill()
        result = _run(skill.run({}))
        assert result.status == SkillStatus.VERIFIED
        assert result.evidence is not None
        assert result.evidence.status == VerificationStatus.VERIFIED

    def test_failing_skill_returns_failed(self):
        skill = FailingSkill()
        result = _run(skill.run({}))
        assert result.status in (SkillStatus.FAILED, SkillStatus.RECOVERY_FAILED)
        assert len(result.errors) > 0

    def test_precondition_fail_stops_execution(self):
        skill = PreconditionFailSkill()
        result = _run(skill.run({}))
        assert result.status == SkillStatus.PRECONDITIONS_FAILED
        assert "Missing required input" in result.errors[0]

    def test_verification_fail_is_reported(self):
        skill = VerificationFailSkill()
        result = _run(skill.run({}))
        assert result.status == SkillStatus.VERIFICATION_FAILED
        assert result.evidence is not None
        assert result.evidence.status == VerificationStatus.FAILED

    def test_blocked_permission_stops_execution(self):
        config = GovernanceConfig(blocked_tools=["shell_execute"])
        policy = PolicyEngine(config)
        skill = BlockedSkill(policy_engine=policy)
        result = _run(skill.run({}))
        assert result.status == SkillStatus.PERMISSION_DENIED

    def test_skill_produces_evidence(self):
        skill = PassingSkill()
        result = _run(skill.run({}))
        assert result.evidence is not None
        assert result.evidence.intent != ""
        assert result.evidence.action != ""
        assert result.evidence.latency_ms >= 0
