#!/usr/bin/env python3
# src/mem_graph/resources/workflows/registry.py
"""Import-time workflow resource registry.

All WorkflowResource definitions are registered here at module load time.
The registry is the single source of truth for workflow metadata —
discovery, dashboard, and runtime selectors all read from here.
"""

from __future__ import annotations

from .models import (
    ProfileSize,
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
)
from .workflow_definitions import GROUP_A_WORKFLOWS

################
#   BUILT-IN WORKFLOWS
################

_AUTOPILOT_WORKFLOW = WorkflowResource(
    key="autopilot_graph",
    display_name="Autopilot Remediation Graph",
    description="Recursive remediation workflow with guard-driven retry. "
    "Context gather → sentry tests → logic draft → style draft → guard → memory sync.",
    profile=ProfileSize.LARGE,
    task_types=["remediation", "refactoring", "bug_fix"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="high",
    source_module="mem_graph.workflows.runtime.orchestrator_runtime",
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Query graph for violations, decisions, map. Pre-read target files.",
            agent="mapper",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="sentry",
            description="Draft failing tests before code authoring.",
            agent="sentry",
            allowed_tools=["file_read"],
            depends_on=["context_gather"],
            artifacts=["sentry_tests"],
        ),
        WorkflowStageDefinition(
            name="logic_draft",
            description="Fixer agent proposes functional code changes.",
            agent="fixer",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["sentry"],
            artifacts=["fixer_patches"],
        ),
        WorkflowStageDefinition(
            name="style_draft",
            description="Scribe agent applies coding standards to logic patches.",
            agent="scribe",
            allowed_tools=["file_read", "file_edit"],
            depends_on=["logic_draft"],
            artifacts=["styled_patches"],
        ),
        WorkflowStageDefinition(
            name="guard",
            description="Run deterministic CLI checks; route to retry or sync.",
            depends_on=["style_draft"],
            artifacts=["validation_status"],
        ),
        WorkflowStageDefinition(
            name="memory_sync",
            description="Persist run outcome to the graph.",
            depends_on=["guard"],
            artifacts=["final_notes"],
        ),
    ],
)

_MANAGED_WORKFLOW = WorkflowResource(
    key="managed_workflow_graph",
    display_name="Managed Sub-Agent Workflow",
    description="Router-selected multi-stage workflow with audit and validation retry control.",
    profile=ProfileSize.LARGE,
    task_types=["subagent_workflow", "managed_workflow"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="medium",
    source_module="mem_graph.workflows.runtime.managed_workflow_runtime",
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read target files.",
            allowed_tools=["file_read", "file_search", "file_grep"],
        ),
        WorkflowStageDefinition(
            name="planning",
            description="Create the stage plan from objective and context.",
            allowed_tools=["file_read"],
            depends_on=["context_gather"],
        ),
        WorkflowStageDefinition(
            name="implementation",
            description="Run implementation with write-capable filesystem tools.",
            agent="fixer",
            allowed_tools=[
                "file_read",
                "file_search",
                "file_grep",
                "file_edit",
                "file_write",
            ],
            depends_on=["planning"],
            artifacts=["implementation_output"],
        ),
        WorkflowStageDefinition(
            name="audit",
            description="Audit implementation output.",
            agent="auditor",
            allowed_tools=["file_read", "file_search", "file_grep"],
            depends_on=["implementation"],
            artifacts=["audit_output"],
        ),
        WorkflowStageDefinition(
            name="debug_validation",
            description="Validate and decide whether to retry.",
            allowed_tools=[
                "file_read",
                "file_search",
                "file_grep",
                "file_edit",
                "file_write",
            ],
            depends_on=["audit"],
            artifacts=["validation_output"],
        ),
        WorkflowStageDefinition(
            name="documentation",
            description="Update project-facing documentation.",
            agent="scribe",
            allowed_tools=[
                "file_read",
                "file_search",
                "file_grep",
                "file_edit",
                "file_write",
            ],
            depends_on=["debug_validation"],
            artifacts=["documentation_output"],
        ),
        WorkflowStageDefinition(
            name="context_map_update",
            description="Refresh context maps after implementation.",
            agent="mapper",
            allowed_tools=[
                "file_read",
                "file_search",
                "file_grep",
                "file_edit",
                "file_write",
            ],
            depends_on=["documentation"],
            artifacts=["context_map_output"],
        ),
        WorkflowStageDefinition(
            name="memory_bank_sync",
            description="Sync memory-bank state before final report.",
            allowed_tools=[
                "file_read",
                "file_search",
                "file_grep",
                "file_edit",
                "file_write",
            ],
            depends_on=["context_map_update"],
        ),
        WorkflowStageDefinition(
            name="final_report",
            description="Produce deterministic final workflow report.",
            depends_on=["memory_bank_sync"],
            artifacts=["final_report"],
        ),
    ],
)

_PACKAGE_AUDIT_WORKFLOW = WorkflowResource(
    key="package_audit",
    display_name="Iterative Package Audit",
    description=(
        "Package-batched audit loop: read 4-5 files per chunk, "
        "produce findings, update running report until all packages are covered."
    ),
    profile=ProfileSize.LARGE,
    task_types=["package_audit", "batched_audit"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module="mem_graph.workflows.runtime.package_audit_runtime",
    stages=[
        WorkflowStageDefinition(
            name="discover_files",
            description="Enumerate all in-scope files grouped by package.",
            allowed_tools=["file_search", "file_grep"],
            artifacts=["file_inventory"],
        ),
        WorkflowStageDefinition(
            name="chunk_package",
            description="Split each package's files into chunks of 4-5.",
            depends_on=["discover_files"],
            artifacts=["chunks"],
        ),
        WorkflowStageDefinition(
            name="analyze_chunk",
            description="Read and analyze a single 4-5 file chunk.",
            agent="auditor",
            allowed_tools=["file_read", "file_grep"],
            depends_on=["chunk_package"],
            artifacts=["chunk_findings"],
        ),
        WorkflowStageDefinition(
            name="update_report",
            description="Append or edit findings into the running report.",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["analyze_chunk"],
            artifacts=["report_section"],
        ),
        WorkflowStageDefinition(
            name="finalize_report",
            description="Deduplicate findings, re-rank severity, produce final report.",
            depends_on=["update_report"],
            artifacts=["final_report"],
        ),
    ],
)

################
#   REGISTRY
################

_WORKFLOW_REGISTRY: dict[str, WorkflowResource] = {
    wf.key: wf
    for wf in [
        _AUTOPILOT_WORKFLOW,
        _MANAGED_WORKFLOW,
        _PACKAGE_AUDIT_WORKFLOW,
        *GROUP_A_WORKFLOWS,
    ]
}


def workflow_registry() -> dict[str, WorkflowResource]:
    """Return the full workflow registry dict (key → WorkflowResource)."""
    return dict(_WORKFLOW_REGISTRY)


def all_workflows() -> list[WorkflowResource]:
    """Return all registered WorkflowResource instances."""
    return list(_WORKFLOW_REGISTRY.values())


def get_workflow(key: str) -> WorkflowResource | None:
    """Return the WorkflowResource for the given key, or None if not found."""
    return _WORKFLOW_REGISTRY.get(key)


def register_workflow(workflow: WorkflowResource) -> None:
    """Register an additional WorkflowResource at runtime.

    Existing entries with the same key are overwritten.
    """
    _WORKFLOW_REGISTRY[workflow.key] = workflow
