from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

FEATURE_IMPLEMENTATION = WorkflowResource(
    key="feature_implementation",
    display_name="Feature Implementation",
    description=(
        "Full-cycle feature build: requirements context, sentry tests, "
        "implementation, audit, documentation, and memory sync."
    ),
    profile=ProfileSize.LARGE,
    task_types=["feature_implementation", "feature", "feature_build"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="high",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read target files and load graph context.",
            agent="mapper",
            allowed_tools=["file_read", "file_search", "file_grep"],
        ),
        WorkflowStageDefinition(
            name="sentry",
            description="Draft failing tests for the new feature.",
            agent="sentry",
            allowed_tools=["file_read"],
            depends_on=["context_gather"],
            artifacts=["sentry_tests"],
        ),
        WorkflowStageDefinition(
            name="implementation",
            description="Implement the feature using fixer agent.",
            agent="fixer",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["sentry"],
            artifacts=["implementation_output"],
        ),
        WorkflowStageDefinition(
            name="audit",
            description="Audit implementation output.",
            agent="auditor",
            allowed_tools=["file_read", "file_grep"],
            depends_on=["implementation"],
            artifacts=["audit_output"],
        ),
        WorkflowStageDefinition(
            name="documentation",
            description="Update project docs for the new feature.",
            agent="scribe",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["audit"],
            artifacts=["documentation_output"],
        ),
        WorkflowStageDefinition(
            name="memory_sync",
            description="Persist run outcome to the graph.",
            depends_on=["documentation"],
            artifacts=["final_notes"],
        ),
    ],
)
