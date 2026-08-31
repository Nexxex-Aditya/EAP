"""Tests for the PolicyEngine per V1 review §18.4, §21, §29."""

import pytest
from eap.core.governance.policy import (
    GovernanceConfig,
    PolicyEngine,
    PermissionVerdict,
    RiskLevel,
)


class TestPolicyEngine:
    """Test policy enforcement."""

    def setup_method(self):
        self.config = GovernanceConfig(
            allowed_browser_domains=["discover.nielseniq.com", "nielseniq.com"],
            macro_whitelist=["InsertColumns", "AutoOpen"],
            blocked_tools=["shell_execute"],
            require_human_for_memory_mutation=True,
            require_human_for_destructive_actions=True,
        )
        self.engine = PolicyEngine(self.config)

    def test_allowed_domain(self):
        result = self.engine.check_browser_navigation("https://discover.nielseniq.com/dashboard")
        assert result.verdict == PermissionVerdict.ALLOWED

    def test_blocked_domain(self):
        result = self.engine.check_browser_navigation("https://evil-site.com/phish")
        assert result.verdict == PermissionVerdict.DENIED

    def test_subdomain_allowed(self):
        result = self.engine.check_browser_navigation("https://app.nielseniq.com/page")
        assert result.verdict == PermissionVerdict.ALLOWED

    def test_whitelisted_macro(self):
        result = self.engine.check_macro_execution("InsertColumns")
        assert result.verdict == PermissionVerdict.ALLOWED

    def test_non_whitelisted_macro_requires_human(self):
        result = self.engine.check_macro_execution("DeleteEverything")
        assert result.verdict == PermissionVerdict.REQUIRES_HUMAN

    def test_blocked_tool(self):
        result = self.engine.check_tool_invocation("shell_execute")
        assert result.verdict == PermissionVerdict.DENIED
        assert result.risk_level == RiskLevel.CRITICAL

    def test_allowed_tool(self):
        result = self.engine.check_tool_invocation("browser_click")
        assert result.verdict == PermissionVerdict.ALLOWED

    def test_memory_mutation_requires_human(self):
        result = self.engine.check_memory_mutation("promote_to_approved")
        assert result.verdict == PermissionVerdict.REQUIRES_HUMAN

    def test_destructive_action_requires_human(self):
        result = self.engine.check_destructive_action("delete_workbook")
        assert result.verdict == PermissionVerdict.REQUIRES_HUMAN

    def test_blocked_directory(self):
        result = self.engine.check_file_access("C:\\Windows\\System32\\cmd.exe", "read")
        assert result.verdict == PermissionVerdict.DENIED
        assert result.risk_level == RiskLevel.CRITICAL

    def test_allowed_file(self):
        result = self.engine.check_file_access("C:\\data\\report.xlsx", "read")
        assert result.verdict == PermissionVerdict.ALLOWED

    def test_audit_log_records_all_checks(self):
        self.engine.check_browser_navigation("https://example.com")
        self.engine.check_macro_execution("InsertColumns")
        self.engine.check_tool_invocation("browser_click")
        log = self.engine.get_audit_log()
        assert len(log) == 3

    def test_denied_actions_filter(self):
        self.engine.check_browser_navigation("https://evil.com")
        self.engine.check_tool_invocation("browser_click")
        denied = self.engine.get_denied_actions()
        assert len(denied) == 1
        assert "evil.com" in denied[0].action


class TestGovernanceConfigDefaults:
    """Test that the default config has sensible security baseline."""

    def test_default_blocked_directories(self):
        config = GovernanceConfig()
        assert "C:\\Windows" in config.blocked_directories

    def test_default_blocked_tools(self):
        config = GovernanceConfig()
        assert "shell_execute" in config.blocked_tools

    def test_default_allowed_extensions(self):
        config = GovernanceConfig()
        assert ".xlsb" in config.allowed_file_extensions
        assert ".xlsx" in config.allowed_file_extensions

    def test_credentials_blocked_by_default(self):
        config = GovernanceConfig()
        assert not config.allow_credentials_in_prompts
        assert not config.allow_credentials_in_logs
