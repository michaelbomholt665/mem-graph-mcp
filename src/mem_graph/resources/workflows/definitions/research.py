from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

RESEARCH = WorkflowResource(
    key="research",
    display_name="Research",
    description=(
        "Cross-cutting research workflow: gather context, explore branches, "
        "synthesize findings, and produce a structured report. "
        "Usable from any lifecycle phase requiring investigation."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["research", "investigation", "spike"],
    reasoning_mode=ReasoningMode.BOUNDED_TOT,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Load relevant files, notes, and graph context.",
            agent="auditor",
            allowed_tools=["file_read", "file_search", "file_grep"],
        ),
        WorkflowStageDefinition(
            name="exploration",
            description="Branch and explore candidate answer paths (≤3).",
            agent="auditor",
            allowed_tools=["file_read", "file_search"],
            depends_on=["context_gather"],
            artifacts=["exploration_branches"],
        ),
        WorkflowStageDefinition(
            name="synthesis",
            description="Prune branches and produce a final findings report.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["exploration"],
            artifacts=["findings_report"],
        ),
    ],
)
