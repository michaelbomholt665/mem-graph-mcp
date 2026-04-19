#!/usr/bin/env python3
# src/mem_graph/workflows/runtime/orchestrator_runtime.py
"""
Orchestrator Runtime: Recursive Autopilot Workflow.

Extracted from agents/orchestrator_graph.py. Consumes a WorkflowSelection
to apply profile-appropriate retry and concurrency policies.

The autopilot_graph and autopilot_graph_run are re-exported here so callers
can import from this module instead of the legacy agent module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ...agents.orchestrator_graph import (
    AutopilotState,
    ContextGatherNode,
    GuardNode,
    LogicDraftNode,
    MemorySyncNode,
    SentryNode,
    StyleDraftNode,
    autopilot_graph,
    autopilot_graph_run,
)
from ...config import ModelTier
from ...resources.workflows.selector import WorkflowSelection, select_all
from .workflow_sandbox import (
    abort_workflow_sandbox,
    ensure_workflow_sandbox,
    finalize_workflow_sandbox,
)

__all__ = [
    "AutopilotState",
    "ContextGatherNode",
    "SentryNode",
    "LogicDraftNode",
    "StyleDraftNode",
    "GuardNode",
    "MemorySyncNode",
    "autopilot_graph",
    "autopilot_graph_run",
    "autopilot_graph_run_with_selection",
]


async def autopilot_graph_run_with_selection(
    language: Literal["go", "python", "typescript"],
    target_files: list[str],
    project_id: str,
    tier: str = ModelTier.STANDARD.value,
    max_retries: int | None = None,
    *,
    selection: WorkflowSelection | None = None,
    task_type: str = "remediation",
    risk_level: str = "high",
) -> AutopilotState:
    """
    Launch the Recursive Autopilot using a profile-selected WorkflowSelection.

    When selection is not provided, one is computed from task_type and
    file count so the profile constraints apply to retry limits and
    concurrency without requiring callers to pre-select.

    Args:
        language: Source language (go, python, typescript).
        target_files: File paths in scope.
        project_id: Project node ID for graph context.
        tier: Model tier string from ModelTier enum.
        max_retries: Maximum refinement loops. Defaults to profile.retry_cycles + 1.
        selection: Pre-computed WorkflowSelection (optional).
        task_type: Task type for automatic selection when selection is None.
        risk_level: Risk hint for automatic selection when selection is None.

    Returns:
        Final AutopilotState.
    """
    if selection is None:
        selection = select_all(
            task_type,
            file_count=len(target_files),
            risk_level=risk_level,
        )

    effective_max_retries = (
        max_retries
        if max_retries is not None
        else max(1, selection.profile.retry_cycles)
    )

    sandbox = await ensure_workflow_sandbox(
        selection,
        {"project_id": project_id, "target_files": target_files},
    )
    effective_target_files = target_files
    if sandbox.enabled and sandbox.workspace_path:
        effective_target_files = [
            str(Path(sandbox.workspace_path) / path)
            if not Path(path).is_absolute()
            else path
            for path in target_files
        ]
    try:
        state = await autopilot_graph_run(
            language=language,
            target_files=effective_target_files,
            project_id=project_id,
            tier=tier,
            max_retries=effective_max_retries,
        )
        finalized = await finalize_workflow_sandbox(
            sandbox,
            validation_passed=state.success and state.validation_status == "approved",
        )
        state.sandbox_session_id = finalized.session_id
        state.sandbox_workspace_path = finalized.workspace_path
        state.sandbox_artifact = finalized.artifact()
        return state
    except Exception:
        await abort_workflow_sandbox(sandbox)
        raise
