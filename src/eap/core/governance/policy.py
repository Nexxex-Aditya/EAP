"""Policy engine — governance guardrails for the EAP platform.

Per V1 review §18.4, §21, §29:
The model must not have unrestricted authority. Every action flows through:

    LLM Decision → PolicyEngine → Permission Check → Executor

The model can PROPOSE. The system VERIFIES. The policy engine ENFORCES.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from eap.core.config import get_logger

logger = get_logger("governance.policy")


class RiskLevel(str, Enum):
    """Risk classification for actions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionVerdict(str, Enum):
    """Result of a permission check."""
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_HUMAN = "requires_human"


class PolicyCheckResult(BaseModel):
    """Result of evaluating an action against the policy engine."""
    action: str
    verdict: PermissionVerdict
    risk_level: RiskLevel = RiskLevel.LOW
    reason: str = ""
    policy_rule: str = ""
    evidence: str = ""


class GovernanceConfig(BaseModel):
    """Configuration for the policy engine.

    Per V1 review §29 — security baseline.
    """
    # Domain restrictions
    allowed_browser_domains: list[str] = Field(default_factory=list)

    # Filesystem restrictions
    allowed_directories: list[str] = Field(default_factory=list)
    allowed_file_extensions: list[str] = Field(
        default_factory=lambda: [".xlsb", ".xlsx", ".xls", ".xlsm", ".csv", ".docx", ".pdf", ".md", ".txt"]
    )
    blocked_directories: list[str] = Field(
        default_factory=lambda: ["C:\\Windows", "C:\\Program Files"]
    )

    # Tool restrictions
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(
        default_factory=lambda: ["shell_execute", "arbitrary_code"]
    )

    # Macro restrictions
    macro_whitelist: list[str] = Field(
        default_factory=lambda: ["InsertColumns", "AutoOpen", "DeveloperMode"]
    )
    require_macro_verification: bool = True

    # High-risk action policy
    require_human_for_high_risk: bool = True
    require_human_for_memory_mutation: bool = True
    require_human_for_destructive_actions: bool = True

    # Credential policy (V1 review §29)
    allow_credentials_in_prompts: bool = False
    allow_credentials_in_logs: bool = False


class PolicyEngine:
    """Enforces governance rules before any action is executed.

    Per V1 review §21: The model cannot decide to skip QC,
    accept approximate values, or declare its own success.
    """

    def __init__(self, config: GovernanceConfig | None = None) -> None:
        self._config = config or GovernanceConfig()
        self._audit_log: list[PolicyCheckResult] = []

    @property
    def config(self) -> GovernanceConfig:
        return self._config

    def check_browser_navigation(self, url: str) -> PolicyCheckResult:
        """Check if navigation to a URL is allowed."""
        if not self._config.allowed_browser_domains:
            # No domain restrictions configured — allow but log warning
            result = PolicyCheckResult(
                action=f"navigate:{url}",
                verdict=PermissionVerdict.ALLOWED,
                risk_level=RiskLevel.MEDIUM,
                reason="No domain allowlist configured — allowing with warning",
                policy_rule="browser.domain_allowlist",
            )
            logger.warning("no_domain_allowlist_configured", url=url)
        else:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.hostname or ""
            allowed = any(
                domain == d or domain.endswith(f".{d}")
                for d in self._config.allowed_browser_domains
            )
            result = PolicyCheckResult(
                action=f"navigate:{url}",
                verdict=PermissionVerdict.ALLOWED if allowed else PermissionVerdict.DENIED,
                risk_level=RiskLevel.LOW if allowed else RiskLevel.HIGH,
                reason=f"Domain '{domain}' {'is' if allowed else 'is NOT'} in allowlist",
                policy_rule="browser.domain_allowlist",
            )

        self._audit_log.append(result)
        return result

    def check_file_access(self, file_path: str, operation: str = "read") -> PolicyCheckResult:
        """Check if file access is allowed."""
        from pathlib import Path
        path = Path(file_path).resolve()

        # Check blocked directories
        for blocked in self._config.blocked_directories:
            if str(path).startswith(blocked):
                result = PolicyCheckResult(
                    action=f"file:{operation}:{file_path}",
                    verdict=PermissionVerdict.DENIED,
                    risk_level=RiskLevel.CRITICAL,
                    reason=f"Path is in blocked directory: {blocked}",
                    policy_rule="filesystem.blocked_directories",
                )
                self._audit_log.append(result)
                return result

        # Check file extension for write operations
        if operation in ("write", "create", "modify"):
            ext = path.suffix.lower()
            if self._config.allowed_file_extensions and ext not in self._config.allowed_file_extensions:
                result = PolicyCheckResult(
                    action=f"file:{operation}:{file_path}",
                    verdict=PermissionVerdict.DENIED,
                    risk_level=RiskLevel.HIGH,
                    reason=f"File extension '{ext}' not in allowed list",
                    policy_rule="filesystem.allowed_extensions",
                )
                self._audit_log.append(result)
                return result

        result = PolicyCheckResult(
            action=f"file:{operation}:{file_path}",
            verdict=PermissionVerdict.ALLOWED,
            risk_level=RiskLevel.LOW,
            reason="File access permitted",
            policy_rule="filesystem.general",
        )
        self._audit_log.append(result)
        return result

    def check_macro_execution(self, macro_name: str) -> PolicyCheckResult:
        """Check if a macro is allowed to execute."""
        allowed = macro_name in self._config.macro_whitelist
        result = PolicyCheckResult(
            action=f"macro:{macro_name}",
            verdict=PermissionVerdict.ALLOWED if allowed else PermissionVerdict.REQUIRES_HUMAN,
            risk_level=RiskLevel.MEDIUM if allowed else RiskLevel.HIGH,
            reason=f"Macro '{macro_name}' {'is' if allowed else 'is NOT'} in whitelist",
            policy_rule="macro.whitelist",
        )
        self._audit_log.append(result)
        return result

    def check_tool_invocation(self, tool_name: str) -> PolicyCheckResult:
        """Check if a tool invocation is permitted."""
        if tool_name in self._config.blocked_tools:
            result = PolicyCheckResult(
                action=f"tool:{tool_name}",
                verdict=PermissionVerdict.DENIED,
                risk_level=RiskLevel.CRITICAL,
                reason=f"Tool '{tool_name}' is explicitly blocked",
                policy_rule="tool.blocked",
            )
        elif self._config.allowed_tools and tool_name not in self._config.allowed_tools:
            result = PolicyCheckResult(
                action=f"tool:{tool_name}",
                verdict=PermissionVerdict.DENIED,
                risk_level=RiskLevel.HIGH,
                reason=f"Tool '{tool_name}' not in allowed tools list",
                policy_rule="tool.allowlist",
            )
        else:
            result = PolicyCheckResult(
                action=f"tool:{tool_name}",
                verdict=PermissionVerdict.ALLOWED,
                risk_level=RiskLevel.LOW,
                reason="Tool invocation permitted",
                policy_rule="tool.general",
            )
        self._audit_log.append(result)
        return result

    def check_memory_mutation(self, operation: str) -> PolicyCheckResult:
        """Check if a memory mutation is allowed."""
        if self._config.require_human_for_memory_mutation:
            result = PolicyCheckResult(
                action=f"memory:{operation}",
                verdict=PermissionVerdict.REQUIRES_HUMAN,
                risk_level=RiskLevel.HIGH,
                reason="Memory mutations require human approval",
                policy_rule="memory.require_human",
            )
        else:
            result = PolicyCheckResult(
                action=f"memory:{operation}",
                verdict=PermissionVerdict.ALLOWED,
                risk_level=RiskLevel.MEDIUM,
                reason="Memory mutation allowed by policy",
                policy_rule="memory.general",
            )
        self._audit_log.append(result)
        return result

    def check_destructive_action(self, action: str) -> PolicyCheckResult:
        """Check if a destructive action requires human approval."""
        if self._config.require_human_for_destructive_actions:
            result = PolicyCheckResult(
                action=f"destructive:{action}",
                verdict=PermissionVerdict.REQUIRES_HUMAN,
                risk_level=RiskLevel.CRITICAL,
                reason="Destructive actions require human approval",
                policy_rule="destructive.require_human",
            )
        else:
            result = PolicyCheckResult(
                action=f"destructive:{action}",
                verdict=PermissionVerdict.ALLOWED,
                risk_level=RiskLevel.HIGH,
                reason="Destructive action allowed by policy — USE CAUTION",
                policy_rule="destructive.general",
            )
        self._audit_log.append(result)
        return result

    def get_audit_log(self) -> list[PolicyCheckResult]:
        """Return the full audit log of policy checks."""
        return list(self._audit_log)

    def get_denied_actions(self) -> list[PolicyCheckResult]:
        """Return only denied policy checks."""
        return [r for r in self._audit_log if r.verdict == PermissionVerdict.DENIED]
