"""Tests for the graph orchestration engine."""

import pytest
import asyncio
from eap.orchestration.graph.engine import (
    GraphBuilder,
    GraphExecutor,
    ExecutionGraph,
    GraphNode,
    NodeStatus,
    NODE_PREPARE_WORKSPACE,
    NODE_FINALIZE,
)
from eap.core.contracts.models import (
    ReportPlan,
    ReportRequest,
    RunState,
    RunStatus,
    TemplateCapability,
)


class TestGraphBuilder:
    def test_builds_graph_with_macros(self):
        template = TemplateCapability(
            has_developer_mode=True,
            has_insert_columns=True,
            has_auto_open=True,
        )
        plan = ReportPlan(template=template)
        builder = GraphBuilder()
        graph = builder.build(plan)

        assert len(graph.nodes) > 0
        node_ids = [n.node_id for n in graph.nodes]
        assert NODE_PREPARE_WORKSPACE in node_ids
        assert NODE_FINALIZE in node_ids
        assert "run_macros" in node_ids

    def test_builds_graph_without_macros(self):
        template = TemplateCapability(
            has_developer_mode=False,
            has_insert_columns=False,
            has_auto_open=False,
        )
        plan = ReportPlan(template=template)
        builder = GraphBuilder()
        graph = builder.build(plan)

        node_ids = [n.node_id for n in graph.nodes]
        assert "run_macros" not in node_ids

    def test_graph_has_correct_dependencies(self):
        plan = ReportPlan(template=TemplateCapability())
        builder = GraphBuilder()
        graph = builder.build(plan)

        # Find finalize node
        finalize = next(n for n in graph.nodes if n.node_id == NODE_FINALIZE)
        assert len(finalize.depends_on) > 0

    def test_graph_with_no_template(self):
        plan = ReportPlan()
        builder = GraphBuilder()
        graph = builder.build(plan)

        # Should still create a valid graph without macro nodes
        assert len(graph.nodes) > 0


class TestGraphExecutor:
    def test_execute_simple_graph(self):
        """Test executing a simple graph with registered handlers."""
        executor = GraphExecutor()

        async def mock_handler(run_state):
            return {"status": "ok"}

        graph = ExecutionGraph(
            nodes=[
                GraphNode(node_id="step1", name="Step 1"),
                GraphNode(node_id="step2", name="Step 2", depends_on=["step1"]),
            ]
        )
        executor.register_handler("step1", mock_handler)
        executor.register_handler("step2", mock_handler)

        run_state = RunState()
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute(graph, run_state)
        )

        assert result.status == RunStatus.COMPLETED
        assert graph.completed

    def test_events_emitted(self):
        executor = GraphExecutor()

        async def mock_handler(run_state):
            return {}

        graph = ExecutionGraph(
            nodes=[GraphNode(node_id="step1", name="Step 1")]
        )
        executor.register_handler("step1", mock_handler)

        run_state = RunState()
        asyncio.get_event_loop().run_until_complete(executor.execute(graph, run_state))

        events = executor.get_events()
        assert len(events) >= 2  # started + completed

    def test_skips_conditional_nodes(self):
        executor = GraphExecutor()
        graph = ExecutionGraph(
            nodes=[
                GraphNode(
                    node_id="skip_me",
                    name="Skip Me",
                    conditional=True,
                    condition_met=False,
                ),
            ]
        )

        run_state = RunState()
        asyncio.get_event_loop().run_until_complete(executor.execute(graph, run_state))

        assert graph.nodes[0].status == NodeStatus.SKIPPED
