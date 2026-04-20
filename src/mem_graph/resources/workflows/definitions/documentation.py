from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

DOCS_GENERATION = WorkflowResource(
    key="docs_generation",
    display_name="Documentation Generation",
    description="Generate API docs, README updates, or module-level documentation.",
    profile=ProfileSize.MEDIUM,
    task_types=["docs_generation", "documentation"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read source modules to document.",
            agent="scribe",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="authoring",
            description="Generate documentation.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["context_gather"],
            artifacts=["generated_docs"],
        ),
    ],
)

CHANGELOG_AUTHORING = WorkflowResource(
    key="changelog_authoring",
    display_name="Changelog Authoring",
    description="Author or update a CHANGELOG from commit history and task context.",
    profile=ProfileSize.SMALL,
    task_types=["changelog_authoring", "changelog"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read commit history, release notes, and existing CHANGELOG.",
            agent="scribe",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="authoring",
            description="Write the CHANGELOG entry.",
            agent="scribe",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["context_gather"],
            artifacts=["changelog_entry"],
        ),
    ],
)

ONBOARDING_DOCS = WorkflowResource(
    key="onboarding_docs",
    display_name="Onboarding Documentation",
    description=(
        "Produce or update developer onboarding materials: "
        "setup guide, architecture overview, and first-run walkthrough."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["onboarding_docs", "developer_onboarding"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read existing docs, README, and project structure.",
            agent="scribe",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="authoring",
            description="Write or update onboarding materials.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["context_gather"],
            artifacts=["onboarding_docs"],
        ),
    ],
)
