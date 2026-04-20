from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

RELEASE_PREPARATION = WorkflowResource(
    key="release_preparation",
    display_name="Release Preparation",
    description=(
        "Prepare a release: bump version, update changelog, "
        "validate build, and tag."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["release_preparation", "release"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="high",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read version files, changelog, and release checklist.",
            agent="auditor",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="preparation",
            description="Bump version and update changelog.",
            agent="scribe",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["context_gather"],
            artifacts=["version_bump", "changelog_update"],
        ),
        WorkflowStageDefinition(
            name="validation",
            description="Validate release artifacts are correct.",
            agent="auditor",
            allowed_tools=["file_read"],
            depends_on=["preparation"],
            artifacts=["release_validation"],
        ),
    ],
)

DEPLOYMENT_VALIDATION = WorkflowResource(
    key="deployment_validation",
    display_name="Deployment Validation",
    description=(
        "Validate deployment configuration and environment readiness "
        "before or after a release."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["deployment_validation", "deploy_check"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="high",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read deployment config and environment specs.",
            agent="auditor",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="validation",
            description="Validate deployment readiness.",
            agent="auditor",
            allowed_tools=["file_read"],
            depends_on=["context_gather"],
            artifacts=["deployment_report"],
        ),
    ],
)
