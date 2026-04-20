from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

PERFORMANCE_PROFILING = WorkflowResource(
    key="performance_profiling",
    display_name="Performance Profiling",
    description=(
        "Bottleneck identification and targeted optimization: "
        "profile hot paths, evaluate optimization branches, apply, and verify."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["performance_profiling", "performance_analysis", "optimization"],
    reasoning_mode=ReasoningMode.BOUNDED_TOT,
    risk_level="medium",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="profiling",
            description="Identify hot paths and bottlenecks.",
            agent="auditor",
            allowed_tools=["file_read", "file_grep"],
        ),
        WorkflowStageDefinition(
            name="optimization",
            description="Apply targeted optimizations with bounded ToT.",
            agent="fixer",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["profiling"],
            artifacts=["optimization_patches"],
        ),
        WorkflowStageDefinition(
            name="verification",
            description="Verify optimization correctness and no regression.",
            agent="auditor",
            allowed_tools=["file_read"],
            depends_on=["optimization"],
            artifacts=["verification_report"],
        ),
        WorkflowStageDefinition(
            name="documentation",
            description="Document performance changes and benchmarks.",
            agent="scribe",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["verification"],
            artifacts=["performance_docs"],
        ),
    ],
)
