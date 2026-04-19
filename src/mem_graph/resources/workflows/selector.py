#!/usr/bin/env python3
# src/mem_graph/resources/workflows/selector.py
"""Workflow and reasoning policy selector.

Provides deterministic selection of:
- WorkflowResource based on task type and risk level.
- WorkflowProfile based on file count, task type, and risk override.
- ReasoningPolicy based on task ambiguity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import (
    ProfileSize,
    ReasoningPolicy,
    WorkflowProfile,
    WorkflowResource,
    WorkflowSandboxPolicy,
)
from .profiles import get_profile
from .reasoning import REACT_CHALLENGE_POLICY, BOUNDED_TOT_POLICY
from .registry import all_workflows, get_workflow
from .task_types import profile_for_task_type


################
#   SELECTION RESULT
################


@dataclass
class WorkflowSelection:
    """Result of a workflow + profile + reasoning policy selection."""

    workflow: WorkflowResource
    profile: WorkflowProfile
    reasoning_policy: ReasoningPolicy
    sandbox_policy: WorkflowSandboxPolicy
    effective_size: ProfileSize
    rationale: str = ""
    overridden: bool = False
    extra: dict[str, object] = field(default_factory=dict)


################
#   SELECTORS
################


def select_workflow(
    task_type: str,
    *,
    preferred_key: str | None = None,
) -> WorkflowResource:
    """Select the best WorkflowResource for the given task type.

    Selection priority:
    1. preferred_key if provided and found in registry.
    2. First workflow whose task_types list contains task_type.
    3. The managed_workflow_graph as fallback.

    Args:
        task_type: Task type string (e.g. 'bug_fix', 'remediation').
        preferred_key: Explicit workflow key override.

    Returns:
        Selected WorkflowResource.
    """
    if preferred_key:
        found = get_workflow(preferred_key)
        if found is not None:
            return found

    for wf in all_workflows():
        if task_type in wf.task_types:
            return wf

    fallback = get_workflow("managed_workflow_graph")
    if fallback is not None:
        return fallback
    return all_workflows()[0]


def select_profile(
    task_type: str,
    file_count: int = 0,
    *,
    risk_level: str = "medium",
    size_override: ProfileSize | None = None,
) -> WorkflowProfile:
    """Select the WorkflowProfile for the given task context.

    Scaling rules applied after task-type base selection:
    - file_count >= 20 → upgrade to LARGE.
    - file_count >= 5 and base is SMALL → upgrade to MEDIUM.
    - risk_level == 'high' → upgrade to at least MEDIUM.
    - size_override takes priority over all rules.

    Args:
        task_type: Task type string.
        file_count: Number of files in scope.
        risk_level: Risk hint.
        size_override: Explicit profile size override.

    Returns:
        Selected WorkflowProfile.
    """
    if size_override is not None:
        return get_profile(size_override)

    base_size = profile_for_task_type(task_type)

    if file_count >= 20:
        base_size = ProfileSize.LARGE
    elif file_count >= 5 and base_size == ProfileSize.SMALL:
        base_size = ProfileSize.MEDIUM

    if risk_level == "high" and base_size == ProfileSize.SMALL:
        base_size = ProfileSize.MEDIUM

    return get_profile(base_size)


def select_reasoning_policy(
    *,
    high_ambiguity: bool = False,
    tot_allowed: bool = False,
) -> ReasoningPolicy:
    """Select the reasoning policy.

    Default is always REACT_CHALLENGE. Bounded ToT is only selected when
    both high_ambiguity and tot_allowed are True.

    Args:
        high_ambiguity: Whether the task is high-ambiguity.
        tot_allowed: Whether Tree-of-Thought is permitted for this run.

    Returns:
        Selected ReasoningPolicy.
    """
    if high_ambiguity and tot_allowed:
        return BOUNDED_TOT_POLICY
    return REACT_CHALLENGE_POLICY


def select_all(
    task_type: str,
    file_count: int = 0,
    *,
    risk_level: str = "medium",
    preferred_key: str | None = None,
    size_override: ProfileSize | None = None,
    high_ambiguity: bool = False,
    tot_allowed: bool = False,
) -> WorkflowSelection:
    """Perform full workflow + profile + reasoning selection in one call.

    Args:
        task_type: Task type string.
        file_count: Number of files in scope.
        risk_level: Risk hint — 'low', 'medium', or 'high'.
        preferred_key: Explicit workflow key override.
        size_override: Explicit profile size override.
        high_ambiguity: Whether the task is high-ambiguity.
        tot_allowed: Whether bounded Tree-of-Thought is permitted.

    Returns:
        WorkflowSelection with workflow, profile, and reasoning policy.
    """
    workflow = select_workflow(
        task_type,
        preferred_key=preferred_key,
    )
    profile = select_profile(
        task_type,
        file_count=file_count,
        risk_level=risk_level,
        size_override=size_override,
    )
    reasoning = select_reasoning_policy(
        high_ambiguity=high_ambiguity,
        tot_allowed=tot_allowed,
    )
    sandbox_policy = workflow.sandbox_policy or profile.sandbox_policy

    overridden = preferred_key is not None or size_override is not None
    rationale_parts = [
        f"task_type={task_type}",
        f"profile={profile.size.value}",
        f"workflow={workflow.key}",
        f"reasoning={reasoning.mode.value}",
        f"sandbox={'enabled' if sandbox_policy.enabled else 'disabled'}",
    ]
    if overridden:
        rationale_parts.append("(explicit override)")

    return WorkflowSelection(
        workflow=workflow,
        profile=profile,
        reasoning_policy=reasoning,
        sandbox_policy=sandbox_policy,
        effective_size=profile.size,
        rationale=", ".join(rationale_parts),
        overridden=overridden,
    )
