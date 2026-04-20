from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

ADR_AUTHORING = WorkflowResource(
    key="adr_authoring",
    display_name="ADR Authoring",
    description="Author a structured Architecture Decision Record for a design choice.",
    profile=ProfileSize.SMALL,
    task_types=["adr_authoring", "architecture_decision"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read existing ADRs and relevant code context.",
            agent="scribe",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="draft",
            description="Draft the ADR with context, options, and rationale.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["context_gather"],
            artifacts=["adr_draft"],
        ),
    ],
)

FEATURE_DESIGN = WorkflowResource(
    key="feature_design",
    display_name="Feature Design",
    description=(
        "Structured feature design: scope, acceptance criteria, "
        "technical approach, and task breakdown."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["feature_design", "design_doc"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read related code and existing design docs.",
            agent="auditor",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="design",
            description="Author the feature design document.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["context_gather"],
            artifacts=["design_document"],
        ),
    ],
)

SCHEMA_DESIGN = WorkflowResource(
    key="schema_design",
    display_name="Schema Design",
    description=(
        "Data model / schema design with bounded ToT for option exploration."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["schema_design", "data_model"],
    reasoning_mode=ReasoningMode.BOUNDED_TOT,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Load existing schemas and domain model context.",
            agent="auditor",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="design",
            description="Design the schema using bounded branch exploration.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["context_gather"],
            artifacts=["schema_document"],
        ),
    ],
)

API_CONTRACT_DESIGN = WorkflowResource(
    key="api_contract_design",
    display_name="API Contract Design",
    description="Design REST or gRPC API contracts with validation surface analysis.",
    profile=ProfileSize.MEDIUM,
    task_types=["api_contract_design", "api_design"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read existing API definitions and client code.",
            agent="auditor",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="design",
            description="Draft the API contract document.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["context_gather"],
            artifacts=["api_contract"],
        ),
    ],
)

DESIGN_DOCS = WorkflowResource(
    key="design_docs",
    display_name="Design Documentation",
    description="Produce or update a design document for an existing subsystem.",
    profile=ProfileSize.SMALL,
    task_types=["design_docs", "design_documentation"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read subsystem code and existing docs.",
            agent="scribe",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="authoring",
            description="Write or update the design document.",
            agent="scribe",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["context_gather"],
            artifacts=["design_docs"],
        ),
    ],
)

RUNBOOK_AUTHORING = WorkflowResource(
    key="runbook_authoring",
    display_name="Runbook Authoring",
    description="Author operational runbooks for deployment, incident, or maintenance tasks.",
    profile=ProfileSize.SMALL,
    task_types=["runbook_authoring", "runbook"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read related code, config, and existing runbooks.",
            agent="scribe",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="authoring",
            description="Write the runbook document.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["context_gather"],
            artifacts=["runbook"],
        ),
    ],
)

DISASTER_RECOVERY = WorkflowResource(
    key="disaster_recovery",
    display_name="Disaster Recovery Planning",
    description=(
        "Design DR strategy using bounded ToT: "
        "identify failure modes, explore mitigations, produce a DR runbook."
    ),
    profile=ProfileSize.MEDIUM,
    task_types=["disaster_recovery", "dr_planning"],
    reasoning_mode=ReasoningMode.BOUNDED_TOT,
    risk_level="high",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="failure_analysis",
            description="Enumerate failure modes and blast radius.",
            agent="auditor",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="strategy",
            description="Design DR strategy using bounded branch exploration.",
            agent="auditor",
            allowed_tools=["file_read"],
            depends_on=["failure_analysis"],
            artifacts=["dr_strategy"],
        ),
        WorkflowStageDefinition(
            name="runbook",
            description="Author the DR runbook.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["strategy"],
            artifacts=["dr_runbook"],
        ),
    ],
)

COMMAND_DESIGN = WorkflowResource(
    key="command_design",
    display_name="Command Design",
    description=(
        "Design CLI commands and sub-commands: "
        "flag surface, help text, validation, and usage examples."
    ),
    profile=ProfileSize.SMALL,
    task_types=["command_design", "cli_design"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read existing CLI entry-points and conventions.",
            agent="scribe",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="design",
            description="Draft command design with flags, help text, and examples.",
            agent="fixer",
            allowed_tools=["file_read", "file_write"],
            depends_on=["context_gather"],
            artifacts=["command_design_doc"],
        ),
    ],
)

ERROR_LOGGING_DESIGN = WorkflowResource(
    key="error_logging_design",
    display_name="Error & Logging Design",
    description=(
        "Design structured error taxonomy and logging strategy: "
        "error codes, log levels, context fields, and alert thresholds."
    ),
    profile=ProfileSize.SMALL,
    task_types=["error_logging_design", "logging_design"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="low",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read existing error handling and logging patterns.",
            agent="auditor",
            allowed_tools=["file_read", "file_search"],
        ),
        WorkflowStageDefinition(
            name="design",
            description="Design the error taxonomy and logging strategy.",
            agent="scribe",
            allowed_tools=["file_read", "file_write"],
            depends_on=["context_gather"],
            artifacts=["error_logging_design_doc"],
        ),
    ],
)
