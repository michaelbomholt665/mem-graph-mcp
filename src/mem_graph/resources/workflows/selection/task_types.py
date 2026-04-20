#!/usr/bin/env python3
# src/mem_graph/resources/workflows/task_types.py
"""Workflow task-type mappings: task categories → preferred profile sizes."""

from __future__ import annotations

from ..models import ProfileSize

################
#   TASK-TYPE → PROFILE MAP
################

#: Map from task category to the preferred ProfileSize for that category.
TASK_TYPE_PROFILE_MAP: dict[str, ProfileSize] = {
    # Low-complexity single-operation tasks → small
    "bug_fix": ProfileSize.SMALL,
    "hotfix": ProfileSize.SMALL,
    "typo": ProfileSize.SMALL,
    "config_change": ProfileSize.SMALL,
    # Authoring / design tasks → small
    "adr_authoring": ProfileSize.SMALL,
    "architecture_decision": ProfileSize.SMALL,
    "design_docs": ProfileSize.SMALL,
    "design_documentation": ProfileSize.SMALL,
    "runbook_authoring": ProfileSize.SMALL,
    "runbook": ProfileSize.SMALL,
    "command_design": ProfileSize.SMALL,
    "cli_design": ProfileSize.SMALL,
    "error_logging_design": ProfileSize.SMALL,
    "logging_design": ProfileSize.SMALL,
    "changelog_authoring": ProfileSize.SMALL,
    "changelog": ProfileSize.SMALL,
    # Standard development tasks → medium
    "refactoring": ProfileSize.MEDIUM,
    "feature": ProfileSize.MEDIUM,
    "documentation": ProfileSize.MEDIUM,
    "test_coverage": ProfileSize.MEDIUM,
    "code_review": ProfileSize.MEDIUM,
    "security_patch": ProfileSize.MEDIUM,
    "dependency_update": ProfileSize.MEDIUM,
    # Group A medium-profile workflows
    "research": ProfileSize.MEDIUM,
    "investigation": ProfileSize.MEDIUM,
    "spike": ProfileSize.MEDIUM,
    "performance_analysis": ProfileSize.MEDIUM,
    "performance_profiling": ProfileSize.MEDIUM,
    "optimization": ProfileSize.MEDIUM,
    "feature_design": ProfileSize.MEDIUM,
    "design_doc": ProfileSize.MEDIUM,
    "schema_design": ProfileSize.MEDIUM,
    "data_model": ProfileSize.MEDIUM,
    "api_contract_design": ProfileSize.MEDIUM,
    "api_design": ProfileSize.MEDIUM,
    "disaster_recovery": ProfileSize.MEDIUM,
    "dr_planning": ProfileSize.MEDIUM,
    "dependency_audit": ProfileSize.MEDIUM,
    "ci_setup": ProfileSize.MEDIUM,
    "ci_configuration": ProfileSize.MEDIUM,
    "docs_generation": ProfileSize.MEDIUM,
    "onboarding_docs": ProfileSize.MEDIUM,
    "developer_onboarding": ProfileSize.MEDIUM,
    "release_preparation": ProfileSize.MEDIUM,
    "release": ProfileSize.MEDIUM,
    "deployment_validation": ProfileSize.MEDIUM,
    "deploy_check": ProfileSize.MEDIUM,
    "utility_extraction": ProfileSize.MEDIUM,
    "extract_utility": ProfileSize.MEDIUM,
    "implementation_planning": ProfileSize.MEDIUM,
    "planning": ProfileSize.MEDIUM,
    "project_scaffold": ProfileSize.MEDIUM,
    "scaffold": ProfileSize.MEDIUM,
    # Complex or high-scope tasks → large
    "remediation": ProfileSize.LARGE,
    "batched_audit": ProfileSize.LARGE,
    "batched_mapping": ProfileSize.LARGE,
    "batched_decision_review": ProfileSize.LARGE,
    "subagent_workflow": ProfileSize.LARGE,
    "managed_workflow": ProfileSize.LARGE,
    "architecture_review": ProfileSize.LARGE,
    "migration": ProfileSize.LARGE,
    "package_audit": ProfileSize.LARGE,
    # Group A large-profile workflows
    "feature_implementation": ProfileSize.LARGE,
    "feature_build": ProfileSize.LARGE,
    "refactor": ProfileSize.LARGE,
    "security_hardening": ProfileSize.LARGE,
    "threat_model": ProfileSize.LARGE,
}

#: Task types grouped by category for discovery/listing.
TASK_TYPE_CATEGORIES: dict[str, list[str]] = {
    "small": [
        "bug_fix",
        "hotfix",
        "typo",
        "config_change",
        "adr_authoring",
        "architecture_decision",
        "design_docs",
        "runbook_authoring",
        "command_design",
        "error_logging_design",
        "changelog_authoring",
    ],
    "medium": [
        "refactoring",
        "feature",
        "documentation",
        "test_coverage",
        "code_review",
        "security_patch",
        "dependency_update",
        "research",
        "investigation",
        "performance_profiling",
        "feature_design",
        "schema_design",
        "api_contract_design",
        "disaster_recovery",
        "dependency_audit",
        "ci_setup",
        "docs_generation",
        "onboarding_docs",
        "release_preparation",
        "deployment_validation",
        "utility_extraction",
        "implementation_planning",
        "project_scaffold",
    ],
    "large": [
        "remediation",
        "batched_audit",
        "batched_mapping",
        "batched_decision_review",
        "subagent_workflow",
        "managed_workflow",
        "architecture_review",
        "migration",
        "package_audit",
        "feature_implementation",
        "refactor",
        "security_hardening",
    ],
}


def profile_for_task_type(task_type: str) -> ProfileSize:
    """Return the preferred ProfileSize for the given task type.

    Falls back to MEDIUM when the task type is not in the map.
    """
    return TASK_TYPE_PROFILE_MAP.get(task_type, ProfileSize.MEDIUM)


def all_task_type_categories() -> dict[str, list[str]]:
    """Return the full task-type → category mapping."""
    return dict(TASK_TYPE_CATEGORIES)
