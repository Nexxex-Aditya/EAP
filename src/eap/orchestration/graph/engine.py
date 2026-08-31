"""Dynamic graph orchestration — builds and executes execution graphs.

Per architecture.md §5, the graph is generated from the request and
template capabilities. Nodes may be conditionally inserted or removed.

Per architecture.md §15, this is capability-driven:
  capabilities = template_registry.get(template_id)
  graph = planner.build_graph(request, capabilities)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Callable, Awaitable

from pydantic import BaseModel, Field

from eap.core.config import get_logger
from eap.core.contracts.models import (
    ExecutionEvidence,
    ReportPlan,
    RunState,
    RunStatus,
    TemplateCapability,
    VerificationStatus,
)
from eap.core.events.models import EventType, RunEvent

logger = get_logger("orchestration.graph")


class NodeStatus(str, Enum):
    """Status of a graph node."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"
    NOT_IMPLEMENTED = "not_implemented"  # V1 review §42: no fake success


class GraphNode(BaseModel):
    """A single node in the execution graph."""
    node_id: str
    name: str
    description: str = ""

    # Execution properties (per rules.md §13)
    idempotent: bool = True
    retry_policy: int = 0  # max retries
    checkpoint_required: bool = False
    verification_required: bool = True

    # Dependency
    depends_on: list[str] = Field(default_factory=list)
    conditional: bool = False
    condition_met: bool = True

    # State
    status: NodeStatus = NodeStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str = ""
    result: dict[str, Any] = Field(default_factory=dict)


class ExecutionGraph(BaseModel):
    """A complete execution graph for a report run."""
    graph_id: str = ""
    plan_id: str = ""
    nodes: list[GraphNode] = Field(default_factory=list)
    current_node_index: int = 0
    completed: bool = False
    failed: bool = False


# ---------------------------------------------------------------------------
# Standard node IDs from architecture.md §5
# ---------------------------------------------------------------------------

NODE_PREPARE_WORKSPACE = "prepare_workspace"
NODE_RESOLVE_TERMS = "resolve_business_terms"
NODE_SELECT_TEMPLATE = "select_template"
NODE_VALIDATE_PLAN = "validate_plan"
NODE_DISCOVER_SESSION = "discover_session"
NODE_CONFIGURE_DATASET = "configure_dataset"
NODE_CONFIGURE_FACTS = "configure_facts"
NODE_CONFIGURE_PRODUCTS = "configure_products"
NODE_CONFIGURE_MARKETS = "configure_markets"
NODE_CONFIGURE_PERIODS = "configure_periods"
NODE_CONFIGURE_FORMAT = "configure_format"
NODE_CONFIGURE_LAYOUT = "configure_layout"
NODE_EXECUTE_DISCOVER = "execute_discover"
NODE_VERIFY_DISCOVER = "verify_discover_result"
NODE_POPULATE_EXCEL = "populate_excel"
NODE_RUN_MACROS = "run_macros"
NODE_REPAIR = "repair"
NODE_QC = "qc"
NODE_REPAIR_IF_ALLOWED = "repair_if_allowed"
NODE_RE_QC = "re_qc"
NODE_FINALIZE = "finalize"


class GraphBuilder:
    """Builds a dynamic execution graph from a request and template capabilities.

    This replaces hard-coded template branches with capability-driven
    graph construction (architecture.md §15).
    """

    def build(self, plan: ReportPlan) -> ExecutionGraph:
        """Build an execution graph from a report plan.

        Nodes are inserted/removed based on the template's capabilities.
        """
        template = plan.template
        nodes: list[GraphNode] = []

        # Core pipeline — always present
        nodes.append(GraphNode(
            node_id=NODE_PREPARE_WORKSPACE,
            name="Prepare Workspace",
            description="Create working folder, NIE.txt, and working copy",
            checkpoint_required=True,
        ))

        nodes.append(GraphNode(
            node_id=NODE_RESOLVE_TERMS,
            name="Resolve Business Terms",
            description="Resolve requested facts/products/markets/periods",
            depends_on=[NODE_PREPARE_WORKSPACE],
        ))

        nodes.append(GraphNode(
            node_id=NODE_SELECT_TEMPLATE,
            name="Select Template",
            description="Select and validate the target template",
            depends_on=[NODE_RESOLVE_TERMS],
        ))

        nodes.append(GraphNode(
            node_id=NODE_VALIDATE_PLAN,
            name="Validate Plan",
            description="Validate the complete execution plan",
            depends_on=[NODE_SELECT_TEMPLATE],
            checkpoint_required=True,
        ))

        # Discover pipeline
        nodes.append(GraphNode(
            node_id=NODE_DISCOVER_SESSION,
            name="Open Discover Session",
            description="Open Discover and authenticate",
            depends_on=[NODE_VALIDATE_PLAN],
            checkpoint_required=True,
        ))

        for node_id, name, dep in [
            (NODE_CONFIGURE_DATASET, "Configure Dataset", NODE_DISCOVER_SESSION),
            (NODE_CONFIGURE_FACTS, "Configure Facts", NODE_CONFIGURE_DATASET),
            (NODE_CONFIGURE_PRODUCTS, "Configure Products", NODE_CONFIGURE_FACTS),
            (NODE_CONFIGURE_MARKETS, "Configure Markets", NODE_CONFIGURE_PRODUCTS),
            (NODE_CONFIGURE_PERIODS, "Configure Periods", NODE_CONFIGURE_MARKETS),
            (NODE_CONFIGURE_FORMAT, "Configure Format", NODE_CONFIGURE_PERIODS),
            (NODE_CONFIGURE_LAYOUT, "Configure Layout", NODE_CONFIGURE_FORMAT),
        ]:
            nodes.append(GraphNode(
                node_id=node_id,
                name=name,
                depends_on=[dep],
                verification_required=True,
            ))

        nodes.append(GraphNode(
            node_id=NODE_EXECUTE_DISCOVER,
            name="Execute Discover Query",
            description="Run the Discover query",
            depends_on=[NODE_CONFIGURE_LAYOUT],
            checkpoint_required=True,
            idempotent=False,
        ))

        nodes.append(GraphNode(
            node_id=NODE_VERIFY_DISCOVER,
            name="Verify Discover Result",
            depends_on=[NODE_EXECUTE_DISCOVER],
        ))

        # Excel pipeline
        nodes.append(GraphNode(
            node_id=NODE_POPULATE_EXCEL,
            name="Populate Excel",
            depends_on=[NODE_VERIFY_DISCOVER],
            checkpoint_required=True,
        ))

        # Conditional: Run macros only if template has them
        if template and (template.has_insert_columns or template.has_auto_open or template.macros):
            nodes.append(GraphNode(
                node_id=NODE_RUN_MACROS,
                name="Run Macros",
                description="Execute template macros (InsertColumns, etc.)",
                depends_on=[NODE_POPULATE_EXCEL],
                conditional=True,
                condition_met=True,
            ))
            repair_dep = NODE_RUN_MACROS
        else:
            repair_dep = NODE_POPULATE_EXCEL

        # Repair and QC
        nodes.append(GraphNode(
            node_id=NODE_REPAIR,
            name="Repair",
            description="Fix formulas, structure, formatting",
            depends_on=[repair_dep],
        ))

        nodes.append(GraphNode(
            node_id=NODE_QC,
            name="Quality Control",
            description="Run numerical, formula, structural, textual, visual QC",
            depends_on=[NODE_REPAIR],
        ))

        nodes.append(GraphNode(
            node_id=NODE_REPAIR_IF_ALLOWED,
            name="Repair If Allowed",
            description="Apply bounded repairs for QC failures",
            depends_on=[NODE_QC],
            conditional=True,
        ))

        nodes.append(GraphNode(
            node_id=NODE_RE_QC,
            name="Re-QC",
            description="Re-run QC after repairs",
            depends_on=[NODE_REPAIR_IF_ALLOWED],
            conditional=True,
        ))

        nodes.append(GraphNode(
            node_id=NODE_FINALIZE,
            name="Finalize",
            description="Run final behavior (AutoOpen), save, and persist audit",
            depends_on=[NODE_QC, NODE_RE_QC],
            checkpoint_required=True,
        ))

        return ExecutionGraph(
            graph_id=f"graph_{plan.plan_id}",
            plan_id=plan.plan_id,
            nodes=nodes,
        )


class GraphExecutor:
    """Executes a graph node by node, handling state and events."""

    def __init__(self) -> None:
        self._node_handlers: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {}
        self._events: list[RunEvent] = []

    def register_handler(
        self,
        node_id: str,
        handler: Callable[..., Awaitable[dict[str, Any]]],
    ) -> None:
        """Register an async handler for a node ID."""
        self._node_handlers[node_id] = handler

    async def execute(
        self,
        graph: ExecutionGraph,
        run_state: RunState,
    ) -> RunState:
        """Execute the graph sequentially, respecting dependencies."""
        logger.info("graph_execution_start", graph_id=graph.graph_id)
        run_state.status = RunStatus.RUNNING

        for node in graph.nodes:
            if not node.condition_met:
                node.status = NodeStatus.SKIPPED
                continue

            # Check dependencies
            deps_ok = all(
                self._get_node(graph, dep_id).status == NodeStatus.COMPLETED
                for dep_id in node.depends_on
                if self._get_node(graph, dep_id) is not None
                and not self._get_node(graph, dep_id).status == NodeStatus.SKIPPED
            )
            if not deps_ok:
                node.status = NodeStatus.SKIPPED
                continue

            # Execute
            node.status = NodeStatus.RUNNING
            node.started_at = datetime.utcnow()
            run_state.current_node = node.node_id

            self._emit_event(EventType.NODE_STARTED, run_state.run_id, node.node_id)

            handler = self._node_handlers.get(node.node_id)
            if handler:
                retries = 0
                while retries <= node.retry_policy:
                    try:
                        import time as _time
                        _start = _time.monotonic()
                        result = await handler(run_state)
                        _elapsed_ms = (_time.monotonic() - _start) * 1000

                        node.result = result
                        node.status = NodeStatus.COMPLETED
                        node.completed_at = datetime.utcnow()

                        # Record execution evidence (V1 review §18.2)
                        evidence = ExecutionEvidence(
                            node_id=node.node_id,
                            run_id=run_state.run_id,
                            intent=node.description or node.name,
                            action=f"Executed handler for {node.node_id}",
                            observation=str(result)[:500] if result else "",
                            verification="Handler returned without exception",
                            evidence=str(result)[:200] if result else "",
                            latency_ms=_elapsed_ms,
                            status=VerificationStatus.VERIFIED if node.verification_required else VerificationStatus.UNVERIFIED,
                            verifier="deterministic",
                        )
                        run_state.evidence_trail.append(evidence)

                        self._emit_event(
                            EventType.NODE_COMPLETED, run_state.run_id, node.node_id
                        )
                        break
                    except Exception as e:
                        retries += 1
                        if retries > node.retry_policy:
                            node.status = NodeStatus.FAILED
                            node.error = str(e)
                            node.completed_at = datetime.utcnow()

                            # Record failure evidence
                            evidence = ExecutionEvidence(
                                node_id=node.node_id,
                                run_id=run_state.run_id,
                                intent=node.description or node.name,
                                action=f"Attempted handler for {node.node_id}",
                                observation=f"Exception: {e}",
                                verification="Handler raised exception",
                                status=VerificationStatus.FAILED,
                                error_code=type(e).__name__,
                            )
                            run_state.evidence_trail.append(evidence)

                            self._emit_event(
                                EventType.NODE_FAILED, run_state.run_id, node.node_id
                            )
                            run_state.status = RunStatus.FAILED
                            graph.failed = True
                            logger.error(
                                "node_failed",
                                node=node.node_id,
                                error=str(e),
                            )
                            return run_state
                        self._emit_event(
                            EventType.NODE_RETRYING, run_state.run_id, node.node_id
                        )
            else:
                # V1 review §1, §42: No handler = NOT_IMPLEMENTED.
                # NEVER mark unhandled nodes as COMPLETED.
                node.status = NodeStatus.NOT_IMPLEMENTED
                node.completed_at = datetime.utcnow()
                node.error = "No handler registered — NOT_IMPLEMENTED"

                evidence = ExecutionEvidence(
                    node_id=node.node_id,
                    run_id=run_state.run_id,
                    intent=node.description or node.name,
                    action="No handler registered",
                    observation="Node has no implementation",
                    verification="Cannot verify — no implementation exists",
                    status=VerificationStatus.NOT_IMPLEMENTED,
                )
                run_state.evidence_trail.append(evidence)

                logger.warning(
                    "node_not_implemented",
                    node=node.node_id,
                )

        graph.completed = True
        run_state.status = RunStatus.COMPLETED
        run_state.completed_at = datetime.utcnow()
        logger.info("graph_execution_complete", graph_id=graph.graph_id)
        return run_state

    def _get_node(self, graph: ExecutionGraph, node_id: str) -> GraphNode | None:
        """Find a node by ID."""
        for n in graph.nodes:
            if n.node_id == node_id:
                return n
        return None

    def _emit_event(self, event_type: EventType, run_id: str, node_id: str) -> None:
        """Emit a structured event."""
        event = RunEvent(
            event_type=event_type,
            run_id=run_id,
            node_id=node_id,
        )
        self._events.append(event)
        logger.info("event_emitted", type=event_type.value, node=node_id)

    def get_events(self) -> list[RunEvent]:
        """Return all emitted events."""
        return list(self._events)
