#!/usr/bin/env python3
# src/mem_graph/resources/workflows/profiles.py
"""Typed workflow profiles for small, medium, and large orchestration runs."""

from __future__ import annotations

from .models import ProfileSize, StagePolicy, WorkflowProfile, WorkflowSandboxPolicy

################
#   SMALL PROFILE
################

SMALL_PROFILE = WorkflowProfile(
    size=ProfileSize.SMALL,
    description=(
        "Minimal stage count, single pass where possible. "
        "Tight tool budget and low fan-out. "
        "Default for low-file, low-risk tasks."
    ),
    max_stages=3,
    fan_out_limit=1,
    retry_cycles=0,
    checkpoint_frequency=0,
    sandbox_policy=WorkflowSandboxPolicy(
        enabled=True,
        memory="512m",
        cpus="1",
        exec_timeout_seconds=20,
        session_ttl_seconds=1800,
        merge_back=True,
    ),
    stage_policies=[
        StagePolicy(
            name="implementation",
            allowed_agents=["fixer"],
            parallel=False,
            retry_allowed=False,
            tool_budget=8,
        ),
        StagePolicy(
            name="validation",
            allowed_agents=["validation"],
            parallel=False,
            retry_allowed=False,
            tool_budget=5,
        ),
    ],
)

################
#   MEDIUM PROFILE
################

MEDIUM_PROFILE = WorkflowProfile(
    size=ProfileSize.MEDIUM,
    description=(
        "Standard staged flow with limited parallel sub-agent fan-out. "
        "One validation/retry cycle allowed by default."
    ),
    max_stages=6,
    fan_out_limit=3,
    retry_cycles=1,
    checkpoint_frequency=0,
    sandbox_policy=WorkflowSandboxPolicy(
        enabled=True,
        memory="1g",
        cpus="2",
        exec_timeout_seconds=30,
        session_ttl_seconds=3600,
        merge_back=True,
    ),
    stage_policies=[
        StagePolicy(
            name="context_gather",
            allowed_agents=["mapper"],
            parallel=False,
            retry_allowed=False,
            tool_budget=10,
        ),
        StagePolicy(
            name="implementation",
            allowed_agents=["fixer", "scribe"],
            parallel=True,
            retry_allowed=True,
            tool_budget=15,
        ),
        StagePolicy(
            name="audit",
            allowed_agents=["auditor"],
            parallel=False,
            retry_allowed=False,
            tool_budget=10,
        ),
        StagePolicy(
            name="validation",
            allowed_agents=["validation"],
            parallel=False,
            retry_allowed=True,
            tool_budget=10,
        ),
    ],
)

################
#   LARGE PROFILE
################

LARGE_PROFILE = WorkflowProfile(
    size=ProfileSize.LARGE,
    description=(
        "Full staged orchestration with milestone loops. "
        "Parallel read/analyze waves followed by implementation/validation waves. "
        "Explicit checkpoints and recovery points."
    ),
    max_stages=10,
    fan_out_limit=6,
    retry_cycles=3,
    checkpoint_frequency=3,
    sandbox_policy=WorkflowSandboxPolicy(
        enabled=True,
        memory="2g",
        cpus="4",
        exec_timeout_seconds=60,
        session_ttl_seconds=7200,
        merge_back=True,
        retain_artifacts=True,
    ),
    stage_policies=[
        StagePolicy(
            name="context_gather",
            allowed_agents=["mapper", "auditor"],
            parallel=True,
            retry_allowed=False,
            tool_budget=20,
        ),
        StagePolicy(
            name="planning",
            allowed_agents=["router"],
            parallel=False,
            retry_allowed=False,
            tool_budget=10,
        ),
        StagePolicy(
            name="implementation",
            allowed_agents=["fixer", "scribe"],
            parallel=True,
            retry_allowed=True,
            tool_budget=25,
        ),
        StagePolicy(
            name="audit",
            allowed_agents=["auditor"],
            parallel=True,
            retry_allowed=True,
            tool_budget=20,
        ),
        StagePolicy(
            name="validation",
            allowed_agents=["validation", "sentry"],
            parallel=False,
            retry_allowed=True,
            tool_budget=15,
        ),
        StagePolicy(
            name="documentation",
            allowed_agents=["scribe"],
            parallel=False,
            retry_allowed=False,
            tool_budget=15,
        ),
        StagePolicy(
            name="memory_sync",
            allowed_agents=["chat"],
            parallel=False,
            retry_allowed=False,
            tool_budget=5,
        ),
    ],
)

################
#   PROFILE MAP
################

PROFILE_MAP: dict[ProfileSize, WorkflowProfile] = {
    ProfileSize.SMALL: SMALL_PROFILE,
    ProfileSize.MEDIUM: MEDIUM_PROFILE,
    ProfileSize.LARGE: LARGE_PROFILE,
}


def get_profile(size: ProfileSize) -> WorkflowProfile:
    """Return the typed WorkflowProfile for the given size."""
    return PROFILE_MAP[size]
