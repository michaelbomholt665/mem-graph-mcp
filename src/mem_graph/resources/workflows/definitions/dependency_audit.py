from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

DEPENDENCY_AUDIT = WorkflowResource(
    key="dependency_audit",
    display_name="Dependency Audit",
    description=(
        "Audit third-party dependencies for version drift, "
        "CVEs, and license compatibility."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["dependency_audit", "dependency_update"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="medium",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="discover",
            description="Enumerate all direct and transitive dependencies.",
            agent="auditor",
            allowed_tools=["file_read", "file_search"],
            artifacts=["dependency_inventory"],
        ),
        WorkflowStageDefinition(
            name="audit",
            description="Evaluate each dependency for CVEs, drift, and license issues.",
            agent="auditor",
            allowed_tools=["file_read"],
            depends_on=["discover"],
            artifacts=["audit_findings"],
        ),
        WorkflowStageDefinition(
            name="report",
            description="Produce the dependency audit report.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["audit"],
            artifacts=["dependency_report"],
        ),
    ],
)

CI_SETUP = WorkflowResource(
    key="ci_setup",
    display_name="CI Setup",
    description=(
        "Configure or improve CI pipeline: "
        "lint, test, build, and deployment stages."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["ci_setup", "ci_configuration"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="medium",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read existing CI config and project structure.",
            agent="auditor",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="implementation",
            description="Write or update CI configuration.",
            agent="fixer",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["context_gather"],
            artifacts=["ci_config"],
        ),
        WorkflowStageDefinition(
            name="validation",
            description="Verify CI configuration is syntactically correct.",
            agent="auditor",
            allowed_tools=["file_read"],
            depends_on=["implementation"],
            artifacts=["ci_validation"],
        ),
    ],
)
