from __future__ import annotations

from dataclasses import dataclass, field

from ..models import (
    ProfileSize,
    ReasoningPolicy,
    WorkflowProfile,
    WorkflowResource,
    WorkflowSandboxPolicy,
)
from ..profiles import get_profile
from ..reasoning import REACT_CHALLENGE_POLICY, BOUNDED_TOT_POLICY
from ..registry import WorkflowRegistry
from .task_types import profile_for_task_type

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


def select_workflow(
    task_type: str,
    *,
    preferred_key: str | None = None,
) -> WorkflowResource:
    if preferred_key:
        workflow = WorkflowRegistry.get_workflow(preferred_key)
        if workflow is not None:
            return workflow

    for wf in WorkflowRegistry.WORKFLOWS:
        if task_type in wf.task_types:
            return wf

    fallback = WorkflowRegistry.get_workflow("managed_workflow_graph")
    return fallback or WorkflowRegistry.WORKFLOWS[0]


def select_profile(
    task_type: str,
    file_count: int = 0,
    *,
    risk_level: str = "medium",
    size_override: ProfileSize | None = None,
) -> WorkflowProfile:
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
    if high_ambiguity and tot_allowed:
        return BOUNDED_TOT_POLICY
    return REACT_CHALLENGE_POLICY


def select_all(
    task_type: str,
    file_count: int = 0,
    *,
    preferred_key: str | None = None,
    risk_level: str = "medium",
    high_ambiguity: bool = False,
    tot_allowed: bool = False,
    size_override: ProfileSize | None = None,
) -> WorkflowSelection:
    wf = select_workflow(task_type, preferred_key=preferred_key)
    profile = select_profile(task_type, file_count, risk_level=risk_level, size_override=size_override)
    reasoning_policy = select_reasoning_policy(high_ambiguity=high_ambiguity, tot_allowed=tot_allowed)
    overridden = preferred_key is not None and wf.key == preferred_key
    sandbox_policy = wf.sandbox_policy or profile.sandbox_policy
    rationale = (
        f"workflow={wf.key}; profile={profile.size.value}; "
        f"reasoning={reasoning_policy.mode.value}; "
        f"sandbox={'enabled' if sandbox_policy.enabled else 'disabled'}"
    )
    
    return WorkflowSelection(
        workflow=wf,
        profile=profile,
        reasoning_policy=reasoning_policy,
        sandbox_policy=sandbox_policy,
        effective_size=profile.size,
        rationale=rationale,
        overridden=overridden,
    )
