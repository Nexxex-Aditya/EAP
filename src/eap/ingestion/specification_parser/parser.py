"""Specification parsers — extract structured requirements from spec documents.

Per prd.md F04, the system ingests DOCX, Markdown, and PDF specifications
and extracts: dimensions, facts, products, markets, periods, format,
layout, macro requirements, QC requirements, and naming conventions.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from eap.core.config import get_logger
from eap.core.contracts.models import (
    LayoutConfig,
    SpecificationProfile,
    SpecificationRequirement,
)

logger = get_logger("ingestion.specification_parser")


# ---------------------------------------------------------------------------
# DOCX Parser
# ---------------------------------------------------------------------------

def parse_docx(file_path: str | Path) -> SpecificationProfile:
    """Parse a DOCX specification file into a SpecificationProfile.

    Uses zipfile + XML parsing (no external deps beyond stdlib for basic parsing).
    Falls back to python-docx for richer extraction if available.
    """
    file_path = Path(file_path)
    logger.info("parsing_docx", file=str(file_path))

    text = _extract_docx_text(file_path)
    file_hash = _compute_hash(file_path)

    profile = _extract_profile_from_text(text)
    profile.source_file = str(file_path)
    profile.source_hash = file_hash

    logger.info(
        "docx_parsed",
        template_name=profile.template_name,
        requirements=len(profile.requirements),
    )
    return profile


def _extract_docx_text(file_path: Path) -> str:
    """Extract plain text from a DOCX file using zipfile."""
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(file_path) as doc:
        xml_content = doc.read("word/document.xml")

    tree = ET.XML(xml_content)
    paragraphs: list[str] = []

    for p in tree.iter(f"{ns}p"):
        texts = [node.text for node in p.iter(f"{ns}t") if node.text]
        if texts:
            paragraphs.append("".join(texts))

    return "\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Markdown Parser
# ---------------------------------------------------------------------------

def parse_markdown(file_path: str | Path) -> SpecificationProfile:
    """Parse a Markdown specification file into a SpecificationProfile."""
    file_path = Path(file_path)
    logger.info("parsing_markdown", file=str(file_path))

    text = file_path.read_text(encoding="utf-8")
    file_hash = _compute_hash(file_path)

    profile = _extract_profile_from_text(text)
    profile.source_file = str(file_path)
    profile.source_hash = file_hash

    return profile


# ---------------------------------------------------------------------------
# PDF Parser
# ---------------------------------------------------------------------------

def parse_pdf(file_path: str | Path) -> SpecificationProfile:
    """Parse a PDF specification file into a SpecificationProfile."""
    file_path = Path(file_path)
    logger.info("parsing_pdf", file=str(file_path))

    try:
        import pdfplumber

        text_parts: list[str] = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        text = "\n".join(text_parts)
    except ImportError:
        logger.warning("pdfplumber_not_available", msg="PDF parsing unavailable")
        text = ""

    file_hash = _compute_hash(file_path)

    profile = _extract_profile_from_text(text)
    profile.source_file = str(file_path)
    profile.source_hash = file_hash

    return profile


# ---------------------------------------------------------------------------
# Generic spec file router
# ---------------------------------------------------------------------------

def parse_specification(file_path: str | Path) -> SpecificationProfile:
    """Route to the correct parser based on file extension."""
    file_path = Path(file_path)
    ext = file_path.suffix.lower()

    if ext == ".docx":
        return parse_docx(file_path)
    elif ext == ".md":
        return parse_markdown(file_path)
    elif ext == ".pdf":
        return parse_pdf(file_path)
    else:
        logger.warning("unsupported_spec_format", ext=ext)
        return SpecificationProfile(source_file=str(file_path))


# ---------------------------------------------------------------------------
# Shared extraction logic
# ---------------------------------------------------------------------------

def _extract_profile_from_text(text: str) -> SpecificationProfile:
    """Extract a SpecificationProfile from raw text content.

    Uses pattern matching to identify template metadata, dimension configs,
    and requirements.
    """
    profile = SpecificationProfile()
    requirements: list[SpecificationRequirement] = []
    lines = text.split("\n")

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        # Template name
        if "template name" in line_stripped.lower() and i + 1 < len(lines):
            profile.template_name = lines[i + 1].strip()
        elif line_stripped.lower().startswith("template name"):
            profile.template_name = line_stripped.split(":", 1)[-1].strip() if ":" in line_stripped else ""

        # View name
        if "view name" in line_stripped.lower() and i + 1 < len(lines):
            profile.view_name = lines[i + 1].strip()

        # Methodology
        if "methodology" in line_stripped.lower():
            if i + 1 < len(lines):
                meth = lines[i + 1].strip().upper()
                if meth in ("VLOOKUP", "PIVOT", "REF"):
                    profile.methodology = meth
            if ":" in line_stripped:
                meth = line_stripped.split(":", 1)[-1].strip().upper()
                if meth in ("VLOOKUP", "PIVOT", "REF"):
                    profile.methodology = meth

        # Dimension layout
        if "rows" in line_stripped.lower() and "dimension" in line_stripped.lower():
            rows_dims = _extract_dimension_list(line_stripped)
            if not profile.dimension_config:
                profile.dimension_config = LayoutConfig()
            if rows_dims:
                profile.dimension_config.rows = rows_dims

        if "columns" in line_stripped.lower() and "dimension" in line_stripped.lower():
            col_dims = _extract_dimension_list(line_stripped)
            if not profile.dimension_config:
                profile.dimension_config = LayoutConfig()
            if col_dims:
                profile.dimension_config.columns = col_dims

        # Facts/Products/Markets/Periods notes
        if line_stripped.lower() == "facts" and i + 1 < len(lines):
            profile.facts_notes = lines[i + 1].strip()
        if line_stripped.lower() == "products" and i + 1 < len(lines):
            profile.products_notes = lines[i + 1].strip()
        if line_stripped.lower() == "markets" and i + 1 < len(lines):
            profile.markets_notes = lines[i + 1].strip()
        if line_stripped.lower() == "periods" and i + 1 < len(lines):
            profile.periods_notes = lines[i + 1].strip()

        # Macro requirements
        if "insertcolumns" in line_stripped.lower():
            if "InsertColumns" not in profile.macro_requirements:
                profile.macro_requirements.append("InsertColumns")

        # NOTE/IMPORTANT lines become requirements
        if line_stripped.upper().startswith("NOTE:") or line_stripped.upper().startswith("IMPORTANT:"):
            requirements.append(SpecificationRequirement(
                dimension="general",
                requirement=line_stripped,
                constraint="",
                notes="",
            ))

    profile.requirements = requirements
    return profile


def _extract_dimension_list(text: str) -> list[str]:
    """Extract dimension names from text like 'Periods, Facts'."""
    known = {"facts", "products", "markets", "periods"}
    found: list[str] = []
    for word in re.split(r"[,\s]+", text):
        if word.lower() in known:
            found.append(word.capitalize())
    return found


def _compute_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Specification Registry
# ---------------------------------------------------------------------------

class SpecificationRegistry:
    """In-memory registry for parsed specifications.

    In production, backed by PostgreSQL.
    """

    def __init__(self) -> None:
        self._specs: dict[str, SpecificationProfile] = {}
        self._hash_index: dict[str, str] = {}

    def register(self, spec: SpecificationProfile) -> str:
        """Register a specification profile. Returns spec_id."""
        if spec.source_hash in self._hash_index:
            return self._hash_index[spec.source_hash]

        self._specs[spec.spec_id] = spec
        if spec.source_hash:
            self._hash_index[spec.source_hash] = spec.spec_id

        logger.info(
            "spec_registered",
            spec_id=spec.spec_id,
            template_name=spec.template_name,
        )
        return spec.spec_id

    def get(self, spec_id: str) -> SpecificationProfile | None:
        """Retrieve a specification by ID."""
        return self._specs.get(spec_id)

    def get_by_template_name(self, template_name: str) -> SpecificationProfile | None:
        """Find a specification by template name (partial match)."""
        name_lower = template_name.lower()
        for s in self._specs.values():
            if name_lower in s.template_name.lower():
                return s
        return None

    def list_all(self) -> list[SpecificationProfile]:
        """List all registered specifications."""
        return list(self._specs.values())

    def scan_directory(self, directory: str | Path) -> list[str]:
        """Parse all spec files in a directory and register them."""
        directory = Path(directory)
        registered: list[str] = []

        for ext in ("*.docx", "*.md", "*.pdf"):
            for fp in directory.glob(ext):
                try:
                    profile = parse_specification(fp)
                    sid = self.register(profile)
                    registered.append(sid)
                except Exception as e:
                    logger.error("spec_parse_failed", file=str(fp), error=str(e))

        return registered
