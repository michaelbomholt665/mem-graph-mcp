from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

REFACTOR = WorkflowResource(
    key="refactor",
    display_name="Refactor",
    description=(
        "Scope-guided refactoring: map dependencies, apply changes, "
        "audit output, and document deltas."
    ),
    profile=ProfileSize.LARGE,
    task_types=["refactor", "refactoring"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="medium",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Map call graph and dependency surface for refactor scope.",
            agent="mapper",
            allowed_tools=["file_read", "file_search", "file_grep"],
        ),
        WorkflowStageDefinition(
            name="implementation",
            description="Apply refactoring changes with fixer agent.",
            agent="fixer",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["context_gather"],
            artifacts=["implementation_output"],
        ),
        WorkflowStageDefinition(
            name="audit",
            description="Verify refactor correctness and style.",
            agent="auditor",
            allowed_tools=["file_read", "file_grep"],
            depends_on=["implementation"],
            artifacts=["audit_output"],
        ),
        WorkflowStageDefinition(
            name="documentation",
            description="Update affected docs and docstrings.",
            agent="scribe",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["audit"],
            artifacts=["documentation_output"],
        ),
        WorkflowStageDefinition(
            name="memory_sync",
            description="Persist refactor outcome to the graph.",
            depends_on=["documentation"],
            artifacts=["final_notes"],
        ),
    ],
)
