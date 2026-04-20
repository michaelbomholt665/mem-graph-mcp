"""Tests for the managed sub-agent workflow graph."""

from __future__ import annotations

import pytest

from mem_graph.agents.router_agent import WorkflowPlan
from mem_graph.agents.workflow_graph import (
    ManagedWorkflowState,
    managed_workflow_graph,
    run_managed_workflow,
)
from mem_graph.workflows.runtime.managed_workflow_runtime import (
    run_managed_workflow_with_selection,
)


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------


def test_managed_workflow_graph_has_nine_nodes() -> None:
    assert len(managed_workflow_graph.get_nodes()) == 9


def test_managed_workflow_graph_node_names() -> None:
    node_names = {n.__name__ for n in managed_workflow_graph.get_nodes()}
    expected = {
        "ContextGatherNode",
        "PlanWorkflowNode",
        "ImplementationNode",
        "AuditNode",
        "DebugOrValidationNode",
        "DocumentationNode",
        "ContextMapUpdateNode",
        "MemoryBankSyncNode",
        "FinalReportNode",
    }
    assert node_names == expected


# ---------------------------------------------------------------------------
# State model
# ---------------------------------------------------------------------------


def test_managed_workflow_state_defaults() -> None:
    state = ManagedWorkflowState(objective="test", project_id="")
    assert state.retry_count == 0
    assert state.max_retries == 3
    assert state.execute_agents is False
    assert state.blockers == []
    assert state.stage_results == []
    assert state.final_report == ""


# ---------------------------------------------------------------------------
# run_managed_workflow (dry-run)
# ---------------------------------------------------------------------------


def _make_plan(**kwargs: object) -> WorkflowPlan:
    defaults: dict[str, object] = {
        "objective": "Test objective",
        "project_id": "proj-test",
        "target_files": [],
        "max_retries": 2,
    }
    defaults.update(kwargs)
    return WorkflowPlan(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_run_managed_workflow_completes_without_agents() -> None:
    plan = _make_plan()
    state = await run_managed_workflow(plan, execute_agents=False)
    assert isinstance(state, ManagedWorkflowState)
    assert state.final_report != ""


@pytest.mark.asyncio
async def test_run_managed_workflow_records_stages() -> None:
    plan = _make_plan()
    state = await run_managed_workflow(plan, execute_agents=False)
    stage_names = [r.stage for r in state.stage_results]
    # At minimum context_gather through final_report should be recorded
    assert "context_gather" in stage_names


@pytest.mark.asyncio
async def test_run_managed_workflow_no_blockers_on_clean_run() -> None:
    plan = _make_plan()
    state = await run_managed_workflow(plan, execute_agents=False)
    assert state.blockers == []


# ---------------------------------------------------------------------------
# run_managed_workflow_with_selection (interface check)
# ---------------------------------------------------------------------------


def test_run_managed_workflow_with_selection_is_callable() -> None:
    import inspect

    assert inspect.iscoroutinefunction(run_managed_workflow_with_selection)
