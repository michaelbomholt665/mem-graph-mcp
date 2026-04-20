from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

IMPLEMENTATION_PLANNING = WorkflowResource(
    key="implementation_planning",
    display_name="Implementation Planning",
    description=(
        "Produce a detailed, phased implementation plan: "
        "scope analysis, task decomposition, risk assessment, and timeline."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["implementation_planning", "planning"],
    reasoning_mode=ReasoningMode.REACT_2,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read codebase context and objective.",
            agent="router",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="planning",
            description="Produce the implementation plan document.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["context_gather"],
            artifacts=["implementation_plan"],
        ),
    ],
)

PROJECT_SCAFFOLD = WorkflowResource(
    key="project_scaffold",
    display_name="Project Scaffold",
    description=(
        "Scaffold a new project or module: "
        "directory structure, config files, CI, and starter documentation."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["project_scaffold", "scaffold"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read project conventions and templates.",
            agent="fixer",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="scaffolding",
            description="Create directory structure and starter files.",
            agent="fixer",
            allowed_tools=["file_write"],
            depends_on=["context_gather"],
            artifacts=["scaffold_files"],
        ),
        WorkflowStageDefinition(
            name="documentation",
            description="Add starter README and CHANGELOG.",
            agent="scribe",
            allowed_tools=["file_write"],
            depends_on=["scaffolding"],
            artifacts=["starter_docs"],
        ),
    ],
)
