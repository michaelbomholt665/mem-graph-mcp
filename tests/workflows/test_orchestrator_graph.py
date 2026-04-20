"""Tests for the autopilot orchestrator graph infrastructure."""

from __future__ import annotations

from mem_graph.agents.orchestrator_graph import (
    AutopilotState,
    ContextGatherNode,
    GuardNode,
    LogicDraftNode,
    MemorySyncNode,
    SentryNode,
    StyleDraftNode,
    autopilot_graph,
)
from mem_graph.workflows.runtime.orchestrator_runtime import (
    autopilot_graph_run_with_selection,
)


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------


def test_autopilot_graph_has_six_nodes() -> None:
    nodes = autopilot_graph.get_nodes()
    assert len(nodes) == 6


def test_autopilot_graph_node_types() -> None:
    node_names = {n.__name__ for n in autopilot_graph.get_nodes()}
    expected = {
        "ContextGatherNode",
        "SentryNode",
        "LogicDraftNode",
        "StyleDraftNode",
        "GuardNode",
        "MemorySyncNode",
    }
    assert node_names == expected


# ---------------------------------------------------------------------------
# State model
# ---------------------------------------------------------------------------


def test_autopilot_state_defaults() -> None:
    state = AutopilotState()
    assert state.language == "python"
    assert state.target_files == []
    assert state.retry_count == 0
    assert state.max_retries == 3
    assert state.success is False
    assert state.validation_status == "pending"


def test_autopilot_state_with_values() -> None:
    state = AutopilotState(
        language="go",
        target_files=["main.go"],
        project_id="proj-1",
        max_retries=5,
    )
    assert state.language == "go"
    assert state.target_files == ["main.go"]
    assert state.project_id == "proj-1"
    assert state.max_retries == 5


# ---------------------------------------------------------------------------
# Node imports from runtime re-export
# ---------------------------------------------------------------------------


def test_orchestrator_runtime_re_exports_nodes() -> None:
    """Verify that the runtime module properly re-exports all node classes."""
    from mem_graph.workflows.runtime.orchestrator_runtime import (
        ContextGatherNode as OrcCtx,
        GuardNode as OrcGuard,
        LogicDraftNode as OrcLogic,
        MemorySyncNode as OrcSync,
        SentryNode as OrcSentry,
        StyleDraftNode as OrcStyle,
        autopilot_graph as orc_graph,
    )

    assert OrcCtx is ContextGatherNode
    assert OrcSentry is SentryNode
    assert OrcLogic is LogicDraftNode
    assert OrcStyle is StyleDraftNode
    assert OrcGuard is GuardNode
    assert OrcSync is MemorySyncNode
    assert orc_graph is autopilot_graph


# ---------------------------------------------------------------------------
# autopilot_graph_run_with_selection interface
# ---------------------------------------------------------------------------


def test_autopilot_graph_run_with_selection_is_callable() -> None:
    import inspect

    assert inspect.iscoroutinefunction(autopilot_graph_run_with_selection)
