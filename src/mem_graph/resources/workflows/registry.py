from __future__ import annotations
from typing import ClassVar
from .models import WorkflowResource
from .definitions import (
    BUILTIN_WORKFLOWS,
    FEATURE_IMPLEMENTATION,
    REFACTOR,
    RESEARCH,
    SECURITY_HARDENING,
    PERFORMANCE_PROFILING,
    ADR_AUTHORING,
    FEATURE_DESIGN,
    SCHEMA_DESIGN,
    API_CONTRACT_DESIGN,
    DESIGN_DOCS,
    RUNBOOK_AUTHORING,
    DISASTER_RECOVERY,
    COMMAND_DESIGN,
    ERROR_LOGGING_DESIGN,
    DEPENDENCY_AUDIT,
    CI_SETUP,
    DOCS_GENERATION,
    CHANGELOG_AUTHORING,
    ONBOARDING_DOCS,
    RELEASE_PREPARATION,
    DEPLOYMENT_VALIDATION,
    UTILITY_EXTRACTION,
    IMPLEMENTATION_PLANNING,
    PROJECT_SCAFFOLD,
)

class WorkflowRegistry:
    WORKFLOWS: ClassVar[list[WorkflowResource]] = [
        *BUILTIN_WORKFLOWS,
        FEATURE_IMPLEMENTATION,
        REFACTOR,
        RESEARCH,
        SECURITY_HARDENING,
        PERFORMANCE_PROFILING,
        ADR_AUTHORING,
        FEATURE_DESIGN,
        SCHEMA_DESIGN,
        API_CONTRACT_DESIGN,
        DESIGN_DOCS,
        RUNBOOK_AUTHORING,
        DISASTER_RECOVERY,
        COMMAND_DESIGN,
        ERROR_LOGGING_DESIGN,
        DEPENDENCY_AUDIT,
        CI_SETUP,
        DOCS_GENERATION,
        CHANGELOG_AUTHORING,
        ONBOARDING_DOCS,
        RELEASE_PREPARATION,
        DEPLOYMENT_VALIDATION,
        UTILITY_EXTRACTION,
        IMPLEMENTATION_PLANNING,
        PROJECT_SCAFFOLD,
    ]
    
    @classmethod
    def get_workflow(cls, key: str) -> WorkflowResource | None:
        for wf in cls.WORKFLOWS:
            if wf.key == key:
                return wf
        return None
        
    @classmethod
    def register_workflow(cls, workflow: WorkflowResource) -> None:
        cls.unregister_workflow(workflow.key)
        cls.WORKFLOWS.append(workflow)

    @classmethod
    def unregister_workflow(cls, key: str) -> None:
        cls.WORKFLOWS[:] = [wf for wf in cls.WORKFLOWS if wf.key != key]

    @classmethod
    def all_workflows(cls) -> list[WorkflowResource]:
        return cls.WORKFLOWS
        
    @classmethod
    def workflow_registry(cls) -> dict[str, WorkflowResource]:
        return {wf.key: wf for wf in cls.WORKFLOWS}

# Backward compatibility
all_workflows = WorkflowRegistry.all_workflows
get_workflow = WorkflowRegistry.get_workflow
register_workflow = WorkflowRegistry.register_workflow
unregister_workflow = WorkflowRegistry.unregister_workflow
workflow_registry = WorkflowRegistry.workflow_registry
WORKFLOWS = WorkflowRegistry.WORKFLOWS
