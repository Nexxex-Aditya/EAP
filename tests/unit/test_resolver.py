"""Tests for the semantic resolver."""

import pytest
from eap.agents.resolver.resolver import SemanticResolver, PeriodResolver
from eap.core.contracts.models import ConfidenceLevel


class TestSemanticResolver:
    def setup_method(self):
        self.resolver = SemanticResolver()

    def test_exact_match(self):
        result = self.resolver.resolve(
            "Sales Value",
            ["Sales Value", "Sales Units", "Price per Unit"],
        )
        assert result.resolved == "Sales Value"
        assert result.confidence == 1.0
        assert result.method == "exact_match"
        assert not result.requires_approval

    def test_exact_match_case_insensitive(self):
        result = self.resolver.resolve(
            "sales value",
            ["Sales Value", "Sales Units"],
        )
        assert result.resolved == "Sales Value"
        assert result.confidence == 1.0

    def test_approved_alias(self):
        self.resolver.register_alias("sv", "Sales Value")
        result = self.resolver.resolve(
            "sv",
            ["Sales Value", "Sales Units"],
        )
        assert result.resolved == "Sales Value"
        assert result.confidence == 0.98
        assert result.method == "approved_alias"

    def test_canonical_synonym(self):
        self.resolver.register_synonym("revenue", "Sales Value")
        result = self.resolver.resolve(
            "revenue",
            ["Sales Value", "Sales Units"],
        )
        assert result.resolved == "Sales Value"
        assert result.confidence == 0.95
        assert result.method == "canonical_synonym"

    def test_language_normalization(self):
        self.resolver.register_language_mapping("umsatz", "Sales Value")
        result = self.resolver.resolve(
            "umsatz",
            ["Sales Value", "Sales Units"],
        )
        assert result.resolved == "Sales Value"
        assert result.method == "language_normalization"

    def test_hierarchy_containment(self):
        result = self.resolver.resolve(
            "Total ALDI",
            ["Total ALDI Market", "State ALDI NSW", "State ALDI VIC"],
        )
        assert result.resolved == "Total ALDI Market"
        assert result.method == "hierarchy_containment"

    def test_unresolvable(self):
        result = self.resolver.resolve(
            "Completely Unknown Term",
            ["Sales Value", "Sales Units"],
        )
        assert result.resolved == ""
        assert result.confidence == 0.0
        assert result.confidence_level == ConfidenceLevel.UNRESOLVABLE
        assert result.requires_approval

    def test_batch_resolve(self):
        results = self.resolver.resolve_batch(
            ["Sales Value", "Sales Units"],
            ["Sales Value", "Sales Units", "Price"],
        )
        assert len(results) == 2
        assert all(r.confidence == 1.0 for r in results)

    def test_any_requires_approval(self):
        results = self.resolver.resolve_batch(
            ["Sales Value", "Unknown"],
            ["Sales Value", "Sales Units"],
        )
        assert self.resolver.any_requires_approval(results)

    def test_validated_mapping(self):
        self.resolver.register_validated_mapping("latest month data", "4 Weeks w/e 11/08/26")
        result = self.resolver.resolve(
            "latest month data",
            ["4 Weeks w/e 11/08/26", "52 Weeks"],
        )
        assert result.resolved == "4 Weeks w/e 11/08/26"
        assert result.method == "historical_validated"


class TestPeriodResolver:
    def setup_method(self):
        self.resolver = SemanticResolver()
        self.period_resolver = PeriodResolver(self.resolver)

    def test_latest_4_weeks(self):
        result = self.period_resolver.resolve_period_expression(
            "latest 4 weeks",
            ["4 Weeks", "52 Weeks", "Months", "Quarters"],
        )
        assert result.resolved == "4 Weeks"
        assert result.method == "period_alias"

    def test_latest_52_weeks(self):
        result = self.period_resolver.resolve_period_expression(
            "latest 52 weeks",
            ["4 Weeks", "52 Weeks", "Months", "Quarters"],
        )
        assert result.resolved == "52 Weeks"

    def test_ytd(self):
        result = self.period_resolver.resolve_period_expression(
            "ytd",
            ["4 Weeks", "Period-to-Date", "Months"],
        )
        assert result.resolved == "Period-to-Date"

    def test_unknown_period_expression(self):
        result = self.period_resolver.resolve_period_expression(
            "last fiscal quarter",
            ["4 Weeks", "52 Weeks", "Months"],
        )
        # Should fall back to general resolver
        assert result.confidence < 0.95 or result.resolved == ""
