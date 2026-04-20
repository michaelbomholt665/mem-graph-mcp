from __future__ import annotations
from ..models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

SECURITY_HARDENING = WorkflowResource(
    key="security_hardening",
    display_name="Security Hardening",
    description=(
        "Threat-model-driven hardening: audit attack surface, "
        "apply mitigations, validate, and document security posture."
    ),
    profile=ProfileSize.LARGE,
    task_types=["security_hardening", "security_patch", "threat_model"],
    reasoning_mode=ReasoningMode.BOUNDED_TOT,
    risk_level="high",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="threat_model",
            description="Identify threats and attack surface using bounded ToT.",
            agent="auditor",
            allowed_tools=["file_read", "file_grep"],
        ),
        WorkflowStageDefinition(
            name="mitigation",
            description="Apply security mitigations with fixer agent.",
            agent="fixer",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["threat_model"],
            artifacts=["mitigation_patches"],
        ),
        WorkflowStageDefinition(
            name="validation",
            description="Validate mitigations against original threat model.",
            agent="auditor",
            allowed_tools=["file_read"],
            depends_on=["mitigation"],
            artifacts=["validation_report"],
        ),
        WorkflowStageDefinition(
            name="documentation",
            description="Document updated security posture and decisions.",
            agent="scribe",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["validation"],
            artifacts=["security_docs"],
        ),
    ],
)
