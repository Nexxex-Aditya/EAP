"""FastAPI application — API layer for the EAP platform.

Per architecture.md §7, this is a thin API layer. Business logic lives
in the domain modules, not in route handlers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from eap.core.config import EAPSettings, configure_logging, get_logger
from eap.core.contracts.models import (
    ReportRequest,
    ReportPlan,
    RunState,
    RunStatus,
    QCResult,
    TemplateCapability,
    TemplateStatus,
)
from eap.ingestion.template_discovery.registry import TemplateRegistry
from eap.ingestion.specification_parser.parser import SpecificationRegistry
from eap.memory.system import MemorySystem

# Initialize
configure_logging()
logger = get_logger("api")
settings = EAPSettings()

app = FastAPI(
    title="EAP — Excel Report Automation Platform",
    description="Enterprise-grade automation for NielsenIQ Discover + Excel reporting",
    version="0.1.0",
)

# In-memory state (production: PostgreSQL)
template_registry = TemplateRegistry()
spec_registry = SpecificationRegistry()
memory_system = MemorySystem()
_runs: dict[str, RunState] = {}
_plans: dict[str, ReportPlan] = {}


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    templates_loaded: int = 0
    active_runs: int = 0


class SubmitReportRequest(BaseModel):
    """API model for submitting a report request."""
    client: str = ""
    description: str = ""
    natural_language_input: str = ""
    dataset_hint: str = ""
    view_hint: str = ""
    template_hint: str = ""
    region: str = ""
    facts: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)
    periods: list[str] = Field(default_factory=list)
    output_name: str = ""


class SubmitReportResponse(BaseModel):
    run_id: str
    request_id: str
    status: str
    message: str = ""


class RunStatusResponse(BaseModel):
    run_id: str
    status: str
    current_node: str = ""
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class TemplateListResponse(BaseModel):
    templates: list[dict[str, Any]]
    total: int


class DashboardResponse(BaseModel):
    active_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    pending_approvals: int = 0
    templates_loaded: int = 0
    recent_runs: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """System health check."""
    return HealthResponse(
        templates_loaded=len(template_registry.list_all()),
        active_runs=sum(1 for r in _runs.values() if r.status == RunStatus.RUNNING),
    )


@app.get("/api/v1/dashboard", response_model=DashboardResponse)
async def get_dashboard() -> DashboardResponse:
    """Dashboard summary for the operations console."""
    runs = list(_runs.values())
    return DashboardResponse(
        active_runs=sum(1 for r in runs if r.status == RunStatus.RUNNING),
        completed_runs=sum(1 for r in runs if r.status == RunStatus.COMPLETED),
        failed_runs=sum(1 for r in runs if r.status == RunStatus.FAILED),
        pending_approvals=sum(1 for r in runs if r.status == RunStatus.NEEDS_REVIEW),
        templates_loaded=len(template_registry.list_all()),
        recent_runs=[
            {
                "run_id": r.run_id,
                "status": r.status.value,
                "current_node": r.current_node,
                "created_at": r.created_at.isoformat(),
            }
            for r in sorted(runs, key=lambda x: x.created_at, reverse=True)[:10]
        ],
    )


@app.post("/api/v1/reports/submit", response_model=SubmitReportResponse)
async def submit_report(request: SubmitReportRequest) -> SubmitReportResponse:
    """Submit a new report request.

    Accepts both natural-language and explicit parameter inputs.
    """
    report_request = ReportRequest(
        client=request.client,
        description=request.description,
        natural_language_input=request.natural_language_input,
        dataset_hint=request.dataset_hint,
        view_hint=request.view_hint,
        template_hint=request.template_hint,
        region=request.region,
        facts=request.facts,
        products=request.products,
        markets=request.markets,
        periods=request.periods,
        output_name=request.output_name,
    )

    # Create run state
    run_state = RunState(request_id=report_request.request_id)
    _runs[run_state.run_id] = run_state

    logger.info(
        "report_submitted",
        run_id=run_state.run_id,
        request_id=report_request.request_id,
        client=request.client,
    )

    return SubmitReportResponse(
        run_id=run_state.run_id,
        request_id=report_request.request_id,
        status=run_state.status.value,
        message="Report request accepted and queued for processing",
    )


@app.get("/api/v1/reports/{run_id}/status", response_model=RunStatusResponse)
async def get_run_status(run_id: str) -> RunStatusResponse:
    """Get the status of a report run."""
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return RunStatusResponse(
        run_id=run.run_id,
        status=run.status.value,
        current_node=run.current_node,
        created_at=run.created_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
        errors=run.errors,
    )


@app.get("/api/v1/templates", response_model=TemplateListResponse)
async def list_templates(status_filter: str | None = None) -> TemplateListResponse:
    """List registered templates."""
    filter_status = None
    if status_filter:
        try:
            filter_status = TemplateStatus(status_filter)
        except ValueError:
            pass

    templates = template_registry.list_all(status=filter_status)
    return TemplateListResponse(
        templates=[
            {
                "template_id": t.template_id,
                "name": t.name,
                "version": t.version,
                "status": t.status.value,
                "methodology": t.methodology,
                "dimension_count": t.dimension_count,
                "has_macros": bool(t.macros),
                "file_hash": t.file_hash[:12] + "..." if t.file_hash else "",
            }
            for t in templates
        ],
        total=len(templates),
    )


@app.post("/api/v1/templates/{template_id}/activate")
async def activate_template(template_id: str) -> dict[str, str]:
    """Activate a template after human review."""
    try:
        template_registry.activate(template_id)
        return {"status": "activated", "template_id": template_id}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/v1/templates/scan")
async def scan_templates(directory: str) -> dict[str, Any]:
    """Scan a directory for Excel templates and register them."""
    try:
        ids = template_registry.scan_and_register_directory(directory)
        return {"scanned": len(ids), "template_ids": ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/runs")
async def list_runs(
    status_filter: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List report runs."""
    runs = list(_runs.values())

    if status_filter:
        try:
            rs = RunStatus(status_filter)
            runs = [r for r in runs if r.status == rs]
        except ValueError:
            pass

    runs.sort(key=lambda x: x.created_at, reverse=True)
    return {
        "runs": [
            {
                "run_id": r.run_id,
                "request_id": r.request_id,
                "status": r.status.value,
                "current_node": r.current_node,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs[:limit]
        ],
        "total": len(runs),
    }


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    """Initialize on startup."""
    logger.info("eap_api_starting", environment=settings.environment)
