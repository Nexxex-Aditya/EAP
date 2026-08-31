"""Semantic resolver — resolves business terms against available choices.

Per rules.md §6, resolution follows this order:
1. Exact match
2. Approved alias
3. Canonical synonym
4. Language normalization
5. Hierarchy-aware matching
6. Context-aware semantic matching
7. Historical validated mapping
8. Human approval

Per rules.md §5, confidence routing:
  >= 0.95: May proceed if verified
  0.80-0.95: Proceed with validated policy
  0.60-0.80: Candidate only, human required
  < 0.60: Stop, do not guess
"""

from __future__ import annotations

from typing import Any

from eap.core.config import EAPSettings, get_logger
from eap.core.contracts.models import (
    ConfidenceLevel,
    ResolutionResult,
)

logger = get_logger("agents.resolver")


class SemanticResolver:
    """Resolves business terms against available Discover choices.

    Uses a layered resolution strategy: deterministic first (exact match,
    alias, synonym), then AI-assisted if needed.
    """

    def __init__(self, settings: EAPSettings | None = None) -> None:
        self._settings = settings or EAPSettings()
        self._aliases: dict[str, str] = {}  # normalized_alias → canonical_name
        self._synonyms: dict[str, str] = {}  # synonym → canonical_name
        self._validated_mappings: dict[str, str] = {}  # historical mappings
        self._language_map: dict[str, str] = {}  # foreign_term → english_term

    def register_alias(self, alias: str, canonical: str) -> None:
        """Register an approved alias mapping."""
        self._aliases[alias.lower().strip()] = canonical
        logger.info("alias_registered", alias=alias, canonical=canonical)

    def register_synonym(self, synonym: str, canonical: str) -> None:
        """Register a canonical synonym."""
        self._synonyms[synonym.lower().strip()] = canonical

    def register_validated_mapping(self, requested: str, resolved: str) -> None:
        """Register a historically validated mapping."""
        self._validated_mappings[requested.lower().strip()] = resolved

    def register_language_mapping(self, foreign: str, english: str) -> None:
        """Register a language normalization mapping."""
        self._language_map[foreign.lower().strip()] = english

    def resolve(
        self,
        requested: str,
        available_choices: list[str],
        *,
        context: dict[str, Any] | None = None,
    ) -> ResolutionResult:
        """Resolve a business term against available choices.

        Follows the resolution order defined in rules.md §6.
        """
        requested_clean = requested.strip()
        requested_lower = requested_clean.lower()

        # 1. Exact match
        for choice in available_choices:
            if choice.lower() == requested_lower:
                return ResolutionResult(
                    requested=requested_clean,
                    resolved=choice,
                    confidence=1.0,
                    confidence_level=ConfidenceLevel.HIGH,
                    method="exact_match",
                )

        # 2. Approved alias
        if requested_lower in self._aliases:
            canonical = self._aliases[requested_lower]
            for choice in available_choices:
                if choice.lower() == canonical.lower():
                    return ResolutionResult(
                        requested=requested_clean,
                        resolved=choice,
                        confidence=0.98,
                        confidence_level=ConfidenceLevel.HIGH,
                        method="approved_alias",
                    )

        # 3. Canonical synonym
        if requested_lower in self._synonyms:
            canonical = self._synonyms[requested_lower]
            for choice in available_choices:
                if choice.lower() == canonical.lower():
                    return ResolutionResult(
                        requested=requested_clean,
                        resolved=choice,
                        confidence=0.95,
                        confidence_level=ConfidenceLevel.HIGH,
                        method="canonical_synonym",
                    )

        # 4. Language normalization
        if requested_lower in self._language_map:
            english = self._language_map[requested_lower]
            for choice in available_choices:
                if choice.lower() == english.lower():
                    return ResolutionResult(
                        requested=requested_clean,
                        resolved=choice,
                        confidence=0.92,
                        confidence_level=ConfidenceLevel.MEDIUM,
                        method="language_normalization",
                    )

        # 5. Hierarchy-aware matching (containment)
        for choice in available_choices:
            if requested_lower in choice.lower() or choice.lower() in requested_lower:
                return ResolutionResult(
                    requested=requested_clean,
                    resolved=choice,
                    confidence=0.85,
                    confidence_level=ConfidenceLevel.MEDIUM,
                    method="hierarchy_containment",
                    alternatives=[c for c in available_choices if c != choice],
                )

        # 6. Context-aware word overlap
        best_score = 0.0
        best_choice = ""
        requested_words = set(requested_lower.split())
        for choice in available_choices:
            choice_words = set(choice.lower().split())
            if not requested_words or not choice_words:
                continue
            overlap = len(requested_words & choice_words)
            total = len(requested_words | choice_words)
            score = overlap / total if total > 0 else 0
            if score > best_score:
                best_score = score
                best_choice = choice

        if best_score >= 0.5:
            confidence = 0.60 + (best_score * 0.20)
            return ResolutionResult(
                requested=requested_clean,
                resolved=best_choice,
                confidence=confidence,
                confidence_level=self._classify_confidence(confidence),
                method="context_word_overlap",
                alternatives=available_choices,
                requires_approval=confidence < self._settings.confidence_medium,
            )

        # 7. Historical validated mapping
        if requested_lower in self._validated_mappings:
            validated = self._validated_mappings[requested_lower]
            for choice in available_choices:
                if choice.lower() == validated.lower():
                    return ResolutionResult(
                        requested=requested_clean,
                        resolved=choice,
                        confidence=0.90,
                        confidence_level=ConfidenceLevel.MEDIUM,
                        method="historical_validated",
                    )

        # 8. Cannot resolve — human approval needed
        logger.warning(
            "resolution_failed",
            requested=requested_clean,
            available_count=len(available_choices),
        )
        return ResolutionResult(
            requested=requested_clean,
            resolved="",
            confidence=0.0,
            confidence_level=ConfidenceLevel.UNRESOLVABLE,
            method="unresolved",
            alternatives=available_choices,
            requires_approval=True,
            evidence=f"No match found for '{requested_clean}' among {len(available_choices)} choices",
        )

    def resolve_batch(
        self,
        requested_items: list[str],
        available_choices: list[str],
        *,
        context: dict[str, Any] | None = None,
    ) -> list[ResolutionResult]:
        """Resolve a batch of business terms."""
        return [
            self.resolve(item, available_choices, context=context)
            for item in requested_items
        ]

    def any_requires_approval(self, results: list[ResolutionResult]) -> bool:
        """Check if any resolution result requires human approval."""
        return any(r.requires_approval for r in results)

    def _classify_confidence(self, confidence: float) -> ConfidenceLevel:
        """Classify a confidence score into a routing level."""
        if confidence >= self._settings.confidence_high:
            return ConfidenceLevel.HIGH
        elif confidence >= self._settings.confidence_medium:
            return ConfidenceLevel.MEDIUM
        elif confidence >= self._settings.confidence_low:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.UNRESOLVABLE


class PeriodResolver:
    """Specialized resolver for period expressions.

    Per rules.md §7, phrases like 'latest month' must be resolved against
    available Discover periods, not translated to hard-coded values.
    """

    def __init__(self, resolver: SemanticResolver) -> None:
        self._resolver = resolver

    # Common period expression aliases
    PERIOD_ALIASES: dict[str, list[str]] = {
        "latest month": ["4 Weeks", "Months", "Current Scan Periods"],
        "latest 4 weeks": ["4 Weeks"],
        "latest 52 weeks": ["52 Weeks", "Years"],
        "latest quarter": ["Quarters"],
        "latest year": ["Years"],
        "year to date": ["Period-to-Date"],
        "ytd": ["Period-to-Date"],
        "mat": ["52 Weeks", "Years"],
        "rolling year": ["52 Weeks"],
    }

    def resolve_period_expression(
        self,
        expression: str,
        available_period_families: list[str],
    ) -> ResolutionResult:
        """Resolve a natural-language period expression.

        First checks known aliases, then falls back to the semantic resolver.
        """
        expr_lower = expression.lower().strip()

        # Check known period aliases
        if expr_lower in self.PERIOD_ALIASES:
            candidates = self.PERIOD_ALIASES[expr_lower]
            for candidate in candidates:
                for family in available_period_families:
                    if candidate.lower() in family.lower():
                        return ResolutionResult(
                            requested=expression,
                            resolved=family,
                            confidence=0.90,
                            confidence_level=ConfidenceLevel.MEDIUM,
                            method="period_alias",
                            alternatives=available_period_families,
                        )

        # Fall back to general resolver
        return self._resolver.resolve(expression, available_period_families)
