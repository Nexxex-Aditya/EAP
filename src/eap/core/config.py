"""EAP platform configuration and logging setup.

Provides structured JSON logging via structlog and application settings
via pydantic-settings.
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings


class EAPSettings(BaseSettings):
    """Application-wide settings loaded from env vars or .env file."""

    # General
    app_name: str = "EAP"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Paths
    workspace_root: Path = Path("./workspaces")
    template_root: Path = Path("./templates")
    artifact_root: Path = Path("./artifacts")

    # Excel
    excel_com_visible: bool = False
    excel_com_timeout_seconds: int = 120

    # Browser
    browser_headless: bool = True
    browser_timeout_ms: int = 30000
    discover_base_url: str = ""
    allowed_browser_domains: list[str] = Field(default_factory=list)

    # Security
    nie_marker_filename: str = "NIE.txt"

    # QC
    default_qc_profile: str = "default"
    max_repair_attempts: int = 3

    # Retry
    max_retries: int = 3
    retry_backoff_base: float = 2.0

    # Confidence thresholds (per rules.md §5)
    confidence_high: float = 0.95
    confidence_medium: float = 0.80
    confidence_low: float = 0.60

    model_config = {"env_prefix": "EAP_", "env_file": ".env", "extra": "ignore"}


def configure_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the EAP platform."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "eap") -> structlog.BoundLogger:
    """Get a named structured logger."""
    return structlog.get_logger(name)


def generate_run_id() -> str:
    """Generate a unique run ID."""
    return str(uuid.uuid4())
