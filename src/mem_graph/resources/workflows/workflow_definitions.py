#!/usr/bin/env python3
# src/mem_graph/resources/workflows/workflow_definitions.py
"""Group A workflow definitions for the mem_graph workflow registry.

All 24 Group A WorkflowResource objects are defined here and registered
into the central WorkflowRegistry via registry.register_workflow().
Group B workflows are blocked on chat_agent / diagram_agent completion.
"""

from __future__ import annotations

from .models import (
    ReasoningMode,
    WorkflowResource,
    WorkflowStageDefinition,
    ProfileSize,
)

_MANAGED_RUNTIME = "mem_graph.workflows.runtime.managed_workflow_runtime"

################
#   PRIORITY 1
################

FEATURE_IMPLEMENTATION = WorkflowResource(
    key="feature_implementation",
    display_name="Feature Implementation",
    description=(
        "Full-cycle feature build: requirements context, sentry tests, "
        "implementation, audit, documentation, and memory sync."
    ),
    profile=ProfileSize.LARGE,
    task_types=["feature_implementation", "feature", "feature_build"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="high",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Read target files and load graph context.",
            agent="mapper",
            allowed_tools=["file_read", "file_search", "file_grep"],
        ),
        WorkflowStageDefinition(
            name="sentry",
            description="Draft failing tests for the new feature.",
            agent="sentry",
            allowed_tools=["file_read"],
            depends_on=["context_gather"],
            artifacts=["sentry_tests"],
        ),
        WorkflowStageDefinition(
            name="implementation",
            description="Implement the feature using fixer agent.",
            agent="fixer",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["sentry"],
            artifacts=["implementation_output"],
        ),
        WorkflowStageDefinition(
            name="audit",
            description="Audit implementation output.",
            agent="auditor",
            allowed_tools=["file_read", "file_grep"],
            depends_on=["implementation"],
            artifacts=["audit_output"],
        ),
        WorkflowStageDefinition(
            name="documentation",
            description="Update project docs for the new feature.",
            agent="scribe",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["audit"],
            artifacts=["documentation_output"],
        ),
        WorkflowStageDefinition(
            name="memory_sync",
            description="Persist run outcome to the graph.",
            depends_on=["documentation"],
            artifacts=["final_notes"],
        ),
    ],
)

################
#   PRIORITY 2
################

REFACTOR = WorkflowResource(
    key="refactor",
    display_name="Refactor",
    description=(
        "Scope-guided refactoring: map dependencies, apply changes, "
        "audit output, and document deltas."
    ),
    profile=ProfileSize.LARGE,
    task_types=["refactor", "refactoring"],
    reasoning_mode=ReasoningMode.REACT_CHALLENGE,
    risk_level="medium",
    source_module=_MANAGED_RUNTIME,
    stages=[
        WorkflowStageDefinition(
            name="context_gather",
            description="Map call graph and dependency surface for refactor scope.",
            agent="mapper",
            allowed_tools=["file_read", "file_search", "file_grep"],
        ),
        WorkflowStageDefinition(
            name="implementation",
            description="Apply refactoring changes with fixer agent.",
            agent="fixer",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["context_gather"],
            artifacts=["implementation_output"],
        ),
        WorkflowStageDefinition(
            name="audit",
            description="Verify refactor correctness and style.",
            agent="auditor",
            allowed_tools=["file_read", "file_grep"],
            depends_on=["implementation"],
            artifacts=["audit_output"],
        ),
        WorkflowStageDefinition(
            name="documentation",
            description="Update affected docs and docstrings.",
            agent="scribe",
            allowed_tools=["file_read", "file_edit", "file_write"],
            depends_on=["audit"],
            artifacts=["documentation_output"],
        ),
        WorkflowStageDefinition(
            name="memory_sync",
            description="Persist refactor outcome to the graph.",
            depends_on=["documentation"],
            artifacts=["final_notes"],
        ),
    ],
)

################
#   PRIORITY 3
################

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

################
#   PRIORITY 4
################

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

################
#   PRIORITY 5
################

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

################
#   PRIORITY 6 — DESIGN & AUTHORING
################

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

################
#   PRIORITY 7
################

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

################
#   PRIORITY 8
################

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

################
#   PRIORITY 9
################

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

################
#   PRIORITY 10
################

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

################
#   PRIORITY 11
################

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

################
#   ALL GROUP A WORKFLOWS
################

#: All 24 Group A WorkflowResource objects in priority order.
GROUP_A_WORKFLOWS: list[WorkflowResource] = [
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
