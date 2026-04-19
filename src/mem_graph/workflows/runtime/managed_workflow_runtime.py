#!/usr/bin/env python3
# src/mem_graph/workflows/runtime/managed_workflow_runtime.py
"""
Managed Workflow Runtime.

Extracted from agents/workflow_graph.py. Consumes a WorkflowSelection
to apply profile-appropriate constraints to the managed sub-agent workflow.
"""

from __future__ import annotations

from ...agents.router_agent import WorkflowPlan
from ...agents.workflow_graph import (
    AuditNode,
    ContextGatherNode,
    ContextMapUpdateNode,
    DebugOrValidationNode,
    DocumentationNode,
    FinalReportNode,
    ImplementationNode,
    ManagedWorkflowState,
    MemoryBankSyncNode,
    PlanWorkflowNode,
    WorkflowStageResult,
    managed_workflow_graph,
    run_managed_workflow,
)
from ...resources.workflows.selector import WorkflowSelection, select_all
from .workflow_sandbox import (
    abort_workflow_sandbox,
    ensure_workflow_sandbox,
    finalize_workflow_sandbox,
)

__all__ = [
    "ManagedWorkflowState",
    "WorkflowStageResult",
    "ContextGatherNode",
    "PlanWorkflowNode",
    "ImplementationNode",
    "AuditNode",
    "DebugOrValidationNode",
    "DocumentationNode",
    "ContextMapUpdateNode",
    "MemoryBankSyncNode",
    "FinalReportNode",
    "managed_workflow_graph",
    "run_managed_workflow",
    "run_managed_workflow_with_selection",
]


async def run_managed_workflow_with_selection(
    plan: WorkflowPlan,
    *,
    execute_agents: bool = False,
    selection: WorkflowSelection | None = None,
    task_type: str = "subagent_workflow",
    risk_level: str = "medium",
) -> ManagedWorkflowState:
    """
    Run the managed workflow with a profile-selected WorkflowSelection.

    When selection is not provided, one is computed from task_type and
    file count so the profile constraints apply to retry limits.

    Args:
        plan: The WorkflowPlan produced by the router agent.
        execute_agents: Whether to actually invoke sub-agents.
        selection: Pre-computed WorkflowSelection (optional).
        task_type: Task type for automatic selection when selection is None.
        risk_level: Risk hint for automatic selection when selection is None.

    Returns:
        Final ManagedWorkflowState.
    """
    if selection is None:
        selection = select_all(
            task_type,
            file_count=len(plan.target_files),
            risk_level=risk_level,
        )

    effective_max_retries = min(
        plan.max_retries,
        selection.profile.retry_cycles
        if selection.profile.retry_cycles > 0
        else plan.max_retries,
    )
    sandbox = await ensure_workflow_sandbox(
        selection,
        {"project_id": plan.project_id, "target_files": plan.target_files},
    )
    target_files = plan.target_files
    if sandbox.enabled and sandbox.workspace_path:
        from pathlib import Path

        target_files = [
            str(Path(sandbox.workspace_path) / path)
            if not Path(path).is_absolute()
            else path
            for path in plan.target_files
        ]
    effective_plan = plan.model_copy(
        update={"max_retries": effective_max_retries, "target_files": target_files}
    )

    try:
        state = await run_managed_workflow(effective_plan, execute_agents=execute_agents)
        finalized = await finalize_workflow_sandbox(
            sandbox,
            validation_passed=not state.blockers,
        )
        state.sandbox_session_id = finalized.session_id
        state.sandbox_workspace_path = finalized.workspace_path
        state.sandbox_artifact = finalized.artifact()
        return state
    except Exception:
        await abort_workflow_sandbox(sandbox)
        raise
