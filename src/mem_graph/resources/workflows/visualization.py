#!/usr/bin/env python3
# src/mem_graph/resources/workflows/visualization.py
"""Generate workflow visualization metadata from the Python workflow registry.

All metadata rendered by the dashboard or API is derived from the registry —
there are no duplicated static graph declarations.
"""

from __future__ import annotations

from typing import Any

from .registry import all_workflows
from .models import WorkflowResource, WorkflowStageDefinition


################
#   MERMAID
################


def _stage_edges(stages: list[WorkflowStageDefinition]) -> list[dict[str, str]]:
    """Build edge list from stage dependency declarations."""
    edges: list[dict[str, str]] = []
    for stage in stages:
        for dep in stage.depends_on:
            edges.append({"source": dep, "target": stage.name, "label": ""})
    return edges


def workflow_to_mermaid(workflow: WorkflowResource) -> str:
    """Render a WorkflowResource as a Mermaid graph TD diagram."""
    lines = ["graph TD"]
    for edge in _stage_edges(workflow.stages):
        source = edge["source"]
        target = edge["target"]
        label = edge.get("label", "")
        if label:
            lines.append(f"  {source} -->|{label}| {target}")
        else:
            lines.append(f"  {source} --> {target}")

    if not any(True for _ in _stage_edges(workflow.stages)):
        # No dependency edges — just list the nodes in order
        nodes = [s.name for s in workflow.stages]
        for i in range(len(nodes) - 1):
            lines.append(f"  {nodes[i]} --> {nodes[i + 1]}")

    return "\n".join(lines)


################
#   FULL METADATA
################


def workflow_metadata(workflow: WorkflowResource) -> dict[str, Any]:
    """Return dashboard-ready metadata dict for a single workflow."""
    edges = _stage_edges(workflow.stages)
    return {
        "key": workflow.key,
        "display_name": workflow.display_name,
        "description": workflow.description,
        "profile": workflow.profile.value,
        "task_types": workflow.task_types,
        "risk_level": workflow.risk_level,
        "reasoning_mode": workflow.reasoning_mode.value,
        "source_module": workflow.source_module,
        "nodes": [s.name for s in workflow.stages],
        "edges": edges,
        "mermaid": workflow_to_mermaid(workflow),
        "stage_count": len(workflow.stages),
    }


def all_workflow_metadata() -> list[dict[str, Any]]:
    """Return dashboard-ready metadata for all registered workflows."""
    return [workflow_metadata(wf) for wf in all_workflows()]
