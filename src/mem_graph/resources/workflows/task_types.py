#!/usr/bin/env python3
# src/mem_graph/resources/workflows/task_types.py
"""Workflow task-type mappings: task categories → preferred profile sizes."""

from __future__ import annotations

from .models import ProfileSize

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
    # Standard development tasks → medium
    "refactoring": ProfileSize.MEDIUM,
    "feature": ProfileSize.MEDIUM,
    "documentation": ProfileSize.MEDIUM,
    "test_coverage": ProfileSize.MEDIUM,
    "code_review": ProfileSize.MEDIUM,
    "security_patch": ProfileSize.MEDIUM,
    "dependency_update": ProfileSize.MEDIUM,
    # Complex or high-scope tasks → large
    "remediation": ProfileSize.LARGE,
    "batched_audit": ProfileSize.LARGE,
    "batched_mapping": ProfileSize.LARGE,
    "batched_decision_review": ProfileSize.LARGE,
    "subagent_workflow": ProfileSize.LARGE,
    "managed_workflow": ProfileSize.LARGE,
    "architecture_review": ProfileSize.LARGE,
    "migration": ProfileSize.LARGE,
    "performance_analysis": ProfileSize.LARGE,
    "package_audit": ProfileSize.LARGE,
}

#: Task types grouped by category for discovery/listing.
TASK_TYPE_CATEGORIES: dict[str, list[str]] = {
    "small": [
        "bug_fix",
        "hotfix",
        "typo",
        "config_change",
    ],
    "medium": [
        "refactoring",
        "feature",
        "documentation",
        "test_coverage",
        "code_review",
        "security_patch",
        "dependency_update",
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
        "performance_analysis",
        "package_audit",
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
