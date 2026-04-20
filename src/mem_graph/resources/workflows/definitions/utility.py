from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

UTILITY_EXTRACTION = WorkflowResource(
    key="utility_extraction",
    display_name="Utility Extraction",
    description=(
        "Identify and extract reusable utilities from existing code: "
        "map, extract, audit, and document."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["utility_extraction", "extract_utility"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="medium",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="mapping",
            description="Map code for extraction candidates.",
            agent="mapper",
            allowed_tools=["file_read", "file_search", "file_grep"],
        ),
        WorkflowStageDefinition(
            name="extraction",
            description="Extract and refactor identified utilities.",
            agent="fixer",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["mapping"],
            artifacts=["extracted_utilities"],
        ),
        WorkflowStageDefinition(
            name="audit",
            description="Audit extracted utilities for correctness.",
            agent="auditor",
            allowed_tools=["file_read"],
            depends_on=["extraction"],
            artifacts=["utility_audit"],
        ),
    ],
)
