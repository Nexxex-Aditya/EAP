"""Abstract skill base class.

Per V1 review §19, every skill must define:
- inputs
- preconditions
- execution
- postconditions
- verification
- evidence
- failure modes
- recovery strategy
- permissions
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from eap.core.contracts.models import (
    ExecutionEvidence,
    VerificationStatus,
)
from eap.core.governance.policy import PolicyEngine, PermissionVerdict
from eap.core.config import get_logger

logger = get_logger("skills.base")


class SkillStatus(str, Enum):
    """Execution status of a skill."""
    NOT_STARTED = "not_started"
    PRECONDITIONS_MET = "preconditions_met"
    PRECONDITIONS_FAILED = "preconditions_failed"
    EXECUTING = "executing"
    EXECUTED = "executed"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    FAILED = "failed"
    RECOVERED = "recovered"
    RECOVERY_FAILED = "recovery_failed"
    PERMISSION_DENIED = "permission_denied"


class SkillDefinition(BaseModel):
    """Declarative definition of a skill's contract."""
    skill_id: str
    name: str
    description: str = ""
    component: str = ""  # "discover", "excel", "qc"

    # What the skill needs
    required_inputs: list[str] = Field(default_factory=list)
    optional_inputs: list[str] = Field(default_factory=list)

    # Preconditions that must be true
    preconditions: list[str] = Field(default_factory=list)

    # Postconditions that must be true after execution
    postconditions: list[str] = Field(default_factory=list)

    # Known failure modes
    failure_modes: list[str] = Field(default_factory=list)

    # Recovery strategies
    recovery_strategies: list[str] = Field(default_factory=list)

    # Required permissions
    required_permissions: list[str] = Field(default_factory=list)

    # Whether this skill is idempotent
    idempotent: bool = True

    # Max retries
    max_retries: int = 1


class SkillResult(BaseModel):
    """Result of executing a skill."""
    skill_id: str
    status: SkillStatus = SkillStatus.NOT_STARTED
    evidence: ExecutionEvidence | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    recovery_attempted: bool = False
    recovery_succeeded: bool = False


class Skill(ABC):
    """Abstract base class for all EAP skills.

    Per V1 review §19, implements the full lifecycle:
    check_permissions → check_preconditions → execute → verify → (recover if needed)

    Every skill produces ExecutionEvidence.
    """

    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self._policy = policy_engine or PolicyEngine()

    @property
    @abstractmethod
    def definition(self) -> SkillDefinition:
        """Return the skill's declarative definition."""

    @abstractmethod
    async def check_preconditions(self, context: dict[str, Any]) -> tuple[bool, str]:
        """Check if preconditions are met.

        Returns (met, reason).
        """

    @abstractmethod
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute the skill's core operation.

        Returns output dict.
        """

    @abstractmethod
    async def verify(self, context: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        """Independently verify the execution result.

        Per V1 review §17: Do NOT allow the same reasoning step
        that performed an action to simply declare it successful.

        Returns (verified, evidence_description).
        """

    async def recover(self, context: dict[str, Any], error: Exception) -> dict[str, Any] | None:
        """Attempt structured recovery per V1 review §20.

        Default: no recovery (returns None).
        Subclasses override for skill-specific recovery.

        Recovery flow:
        1. Classify failure
        2. Retrieve known recovery strategy
        3. Check whether recovery is safe
        4. Execute recovery
        5. Verify
        6. Continue OR escalate
        """
        return None

    def check_permissions(self) -> tuple[bool, str]:
        """Check if the policy engine permits this skill."""
        for perm in self.definition.required_permissions:
            result = self._policy.check_tool_invocation(perm)
            if result.verdict == PermissionVerdict.DENIED:
                return False, f"Permission denied: {perm} — {result.reason}"
            if result.verdict == PermissionVerdict.REQUIRES_HUMAN:
                return False, f"Requires human approval: {perm}"
        return True, "All permissions granted"

    async def run(self, context: dict[str, Any]) -> SkillResult:
        """Full lifecycle execution of the skill.

        This is the main entry point. It orchestrates:
        1. Permission check
        2. Precondition check
        3. Execution
        4. Verification
        5. Recovery (if execution or verification fails)
        """
        import time
        skill_id = self.definition.skill_id
        result = SkillResult(skill_id=skill_id)

        # 1. Permission check
        perm_ok, perm_reason = self.check_permissions()
        if not perm_ok:
            result.status = SkillStatus.PERMISSION_DENIED
            result.errors.append(perm_reason)
            logger.warning("skill_permission_denied", skill=skill_id, reason=perm_reason)
            return result

        # 2. Precondition check
        pre_ok, pre_reason = await self.check_preconditions(context)
        if not pre_ok:
            result.status = SkillStatus.PRECONDITIONS_FAILED
            result.errors.append(f"Precondition failed: {pre_reason}")
            logger.warning("skill_precondition_failed", skill=skill_id, reason=pre_reason)
            return result

        result.status = SkillStatus.PRECONDITIONS_MET

        # 3. Execute
        start = time.monotonic()
        try:
            result.status = SkillStatus.EXECUTING
            output = await self.execute(context)
            elapsed_ms = (time.monotonic() - start) * 1000
            result.output = output
            result.status = SkillStatus.EXECUTED
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            result.status = SkillStatus.FAILED
            result.errors.append(str(e))

            # 5. Recovery
            logger.info("skill_attempting_recovery", skill=skill_id, error=str(e))
            try:
                recovery_result = await self.recover(context, e)
                if recovery_result is not None:
                    result.output = recovery_result
                    result.recovery_attempted = True
                    result.recovery_succeeded = True
                    result.status = SkillStatus.RECOVERED
                else:
                    result.recovery_attempted = True
                    result.recovery_succeeded = False
                    result.status = SkillStatus.RECOVERY_FAILED
            except Exception as re:
                result.recovery_attempted = True
                result.recovery_succeeded = False
                result.status = SkillStatus.RECOVERY_FAILED
                result.errors.append(f"Recovery failed: {re}")

            result.evidence = ExecutionEvidence(
                node_id=skill_id,
                intent=self.definition.description,
                action=f"Executed skill {skill_id}",
                observation=f"Failed: {e}",
                verification="Execution raised exception",
                status=VerificationStatus.FAILED,
                latency_ms=elapsed_ms,
                error_code=type(e).__name__,
            )
            return result

        # 4. Verification
        result.status = SkillStatus.VERIFYING
        verified, verify_evidence = await self.verify(context, output)

        result.evidence = ExecutionEvidence(
            node_id=skill_id,
            intent=self.definition.description,
            action=f"Executed skill {skill_id}",
            observation=str(output)[:500],
            verification=verify_evidence,
            evidence=verify_evidence,
            status=VerificationStatus.VERIFIED if verified else VerificationStatus.FAILED,
            latency_ms=elapsed_ms,
            verifier="deterministic",
        )

        if verified:
            result.status = SkillStatus.VERIFIED
        else:
            result.status = SkillStatus.VERIFICATION_FAILED
            result.errors.append(f"Verification failed: {verify_evidence}")

        logger.info(
            "skill_completed",
            skill=skill_id,
            status=result.status.value,
            latency_ms=elapsed_ms,
        )
        return result
