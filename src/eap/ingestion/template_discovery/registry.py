"""Template registry — manages template versions, capabilities, and activation.

Per architecture.md §15, the platform is configuration-driven and
capability-driven, not template-driven through hard-coded branches.
The registry stores TemplateCapability profiles and resolves the best
template for a given request.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from eap.core.config import get_logger
from eap.core.contracts.models import TemplateCapability, TemplateStatus
from eap.core.errors.exceptions import ConfigurationError

logger = get_logger("ingestion.template_registry")


class TemplateRegistry:
    """In-memory template registry.

    In production, this would be backed by PostgreSQL (architecture.md §10).
    For now, it stores templates in memory with file-hash deduplication.
    """

    def __init__(self) -> None:
        self._templates: dict[str, TemplateCapability] = {}
        self._hash_index: dict[str, str] = {}  # file_hash → template_id

    def register(self, template: TemplateCapability) -> str:
        """Register a new template or update if hash already exists.

        Returns the template_id.
        """
        # Deduplicate by hash
        if template.file_hash in self._hash_index:
            existing_id = self._hash_index[template.file_hash]
            logger.info(
                "template_already_registered",
                template_id=existing_id,
                hash=template.file_hash,
            )
            return existing_id

        self._templates[template.template_id] = template
        if template.file_hash:
            self._hash_index[template.file_hash] = template.template_id

        logger.info(
            "template_registered",
            template_id=template.template_id,
            name=template.name,
            status=template.status.value,
        )
        return template.template_id

    def get(self, template_id: str) -> TemplateCapability | None:
        """Retrieve a template by ID."""
        return self._templates.get(template_id)

    def get_by_hash(self, file_hash: str) -> TemplateCapability | None:
        """Retrieve a template by file hash."""
        tid = self._hash_index.get(file_hash)
        return self._templates.get(tid) if tid else None

    def get_by_name(self, name: str) -> TemplateCapability | None:
        """Retrieve a template by name (case-insensitive partial match)."""
        name_lower = name.lower()
        for t in self._templates.values():
            if name_lower in t.name.lower():
                return t
        return None

    def list_all(self, *, status: TemplateStatus | None = None) -> list[TemplateCapability]:
        """List all templates, optionally filtered by status."""
        templates = list(self._templates.values())
        if status is not None:
            templates = [t for t in templates if t.status == status]
        return templates

    def list_activated(self) -> list[TemplateCapability]:
        """List only activated templates."""
        return self.list_all(status=TemplateStatus.ACTIVATED)

    def activate(self, template_id: str) -> None:
        """Activate a template (after human review)."""
        t = self._templates.get(template_id)
        if t is None:
            raise ConfigurationError(f"Template not found: {template_id}")
        t.status = TemplateStatus.ACTIVATED
        logger.info("template_activated", template_id=template_id, name=t.name)

    def deprecate(self, template_id: str) -> None:
        """Deprecate a template."""
        t = self._templates.get(template_id)
        if t is None:
            raise ConfigurationError(f"Template not found: {template_id}")
        t.status = TemplateStatus.DEPRECATED
        logger.info("template_deprecated", template_id=template_id, name=t.name)

    def find_best_match(
        self,
        *,
        methodology: str = "",
        dimension_count: int | None = None,
        template_hint: str = "",
    ) -> TemplateCapability | None:
        """Find the best matching activated template for the given criteria.

        This is the capability-driven selection that replaces hard-coded
        template branches (architecture.md §15).
        """
        candidates = self.list_activated()

        if template_hint:
            # Direct name match takes priority
            hint_lower = template_hint.lower()
            for t in candidates:
                if hint_lower in t.name.lower():
                    return t

        # Score candidates
        scored: list[tuple[int, TemplateCapability]] = []
        for t in candidates:
            score = 0
            if methodology and t.methodology.lower() == methodology.lower():
                score += 10
            if dimension_count is not None and t.dimension_count == dimension_count:
                score += 5
            scored.append((score, t))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    def scan_and_register_directory(self, directory: str | Path) -> list[str]:
        """Scan a directory for Excel templates and register them.

        Returns list of registered template_ids.
        """
        from eap.ingestion.workbook_scanner.scanner import scan_workbook_com

        directory = Path(directory)
        registered: list[str] = []

        for file_path in directory.glob("*.xlsb"):
            try:
                capability = scan_workbook_com(file_path)
                tid = self.register(capability)
                registered.append(tid)
            except Exception as e:
                logger.error(
                    "template_scan_failed",
                    file=str(file_path),
                    error=str(e),
                )

        # Also scan .xlsx files
        for file_path in directory.glob("*.xlsx"):
            try:
                capability = scan_workbook_com(file_path)
                tid = self.register(capability)
                registered.append(tid)
            except Exception as e:
                logger.error(
                    "template_scan_failed",
                    file=str(file_path),
                    error=str(e),
                )

        logger.info(
            "directory_scan_complete",
            directory=str(directory),
            templates_found=len(registered),
        )
        return registered
