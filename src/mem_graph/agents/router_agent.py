#!/usr/bin/env python3
# src/mem_graph/agents/router_agent.py
"""
Router Agent — intent classifier, tier selector, and task decomposer.

The gateway for all autonomous runs. Reads the graph context first, then
classifies the incoming request by complexity to select the appropriate
model tier. Decomposes multi-file tasks into ordered sub-tasks so the
downstream pipeline handles each unit at the right granularity.
"""

from __future__ import annotations

################
#   IMPORTS
################
import logging
from dataclasses import dataclass, field
from typing import Literal

from pydantic_ai import Agent, RunContext

from ..capabilities import ReasoningStrategyCapability
from ..config import (
    DEFER_AGENT_MODEL_CHECK,
    ModelTier,
    config_get_concurrency_for_files,
    config_get_model_for_tier,
    config_is_solo_mode,
)
from ..models.agent_outputs import (
    RouterDecision,
)
from ..models.agent_outputs import (
    WorkflowPlan as WorkflowPlan,
)
from ..resources.personas import ROUTER_PERSONA

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

_ROUTER_MODEL = config_get_model_for_tier(ModelTier.TURBO)

################
#   DEPS
################


@dataclass
class RouterDependencies:
    """
    Injectable dependencies for the Router Agent.

    Attributes:
        project_id: The project to route for (used for graph context).
        request: The raw user request or task description.
        file_paths: Files in scope for this request.
        context_violations: Open violations from the graph (summary).
        context_decisions: Active decisions from the graph (summary).
        skills_content: Optional SKILL.md content for extra guidance.
    """

    project_id: str
    request: str
    file_paths: list[str] = field(default_factory=list)
    context_violations: list[str] = field(default_factory=list)
    context_decisions: list[str] = field(default_factory=list)
    skills_content: str = ""
    project_root: str = ""
    workflow_mode: Literal["route_only", "subagent_workflow"] = "route_only"
    model_overrides: dict[str, str] = field(default_factory=dict)
    max_retries: int = 3
    reasoning_mode: str = ""


################
#   AGENT
################

router_agent: Agent[RouterDependencies, RouterDecision] = Agent(
    _ROUTER_MODEL,
    name="router",
    deps_type=RouterDependencies,
    output_type=RouterDecision,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
    capabilities=[ReasoningStrategyCapability()],
)


@router_agent.instructions
async def router_build_instructions(ctx: RunContext[RouterDependencies]) -> str:
    """
    Build the Router Agent system prompt.

    Injects the Gateway persona and tier selection rules so the agent
    always grounds its decision in graph context and complexity signals.

    Args:
        ctx: The run context with RouterDependencies.

    Returns:
        Complete system prompt string.
    """
    file_count = len(ctx.deps.file_paths)
    concurrency = config_get_concurrency_for_files(file_count)

    if ctx.deps.workflow_mode == "subagent_workflow":
        mode_note = (
            "Produce a workflow_plan because the caller explicitly requested "
            "subagent_workflow mode. The plan must include required_stages, "
            "stage dependencies, model overrides, allowed tools per stage, "
            "max_retries, and ask-user policy."
        )
    else:
        mode_note = (
            "Default route_only mode. Do not produce a workflow_plan. "
            "Return tier, file_count, concurrency, solo_mode, intent, summary, "
            "and an ordered sub_tasks list."
        )

    return f"""{ROUTER_PERSONA.get_system_instructions()}

## Your Task
Classify the incoming request, select the appropriate model tier, and
decompose the work into ordered sub-tasks.

Workflow mode: {ctx.deps.workflow_mode}. {mode_note}

## File Scope
{file_count} file(s) in scope. Recommended concurrency: {concurrency} worker(s).

## Open Violations (graph context)
{chr(10).join(ctx.deps.context_violations[:20]) or "None"}

## Active Decisions (graph context)
{chr(10).join(ctx.deps.context_decisions[:10]) or "None"}

## Project Helper Agents
Call `router_list_project_helper_agents` when project_root is available and
project-specific helper agents could improve routing.

## Tier Selection
Use `router_compute_tier_hint` for deterministic tier, concurrency, and
solo-mode hints. Explain only intentional overrides.

{ctx.deps.skills_content}
"""


@router_agent.tool
async def router_list_scope_files(
    ctx: RunContext[RouterDependencies],
) -> list[str]:
    """
    Return the file paths in scope for this routing decision.

    Allows the agent to inspect what files are available before
    committing to a tier and concurrency recommendation.

    Args:
        ctx: The run context with RouterDependencies.

    Returns:
        List of file paths from the request scope.
    """
    return ctx.deps.file_paths


@router_agent.tool
async def router_compute_tier_hint(
    ctx: RunContext[RouterDependencies],
    file_count: int,
    edit_count_estimate: int,
) -> str:
    """
    Compute a deterministic tier hint from file and edit estimates.

    Applies the scaling rules from the spec to provide a concrete
    recommendation the agent can accept or override.

    Args:
        ctx: The run context with RouterDependencies.
        file_count: Number of files the task will touch.
        edit_count_estimate: Agent's estimate of total edits required.

    Returns:
        A tier hint string: 'turbo', 'micro', 'standard', or 'autopilot'.
    """
    if edit_count_estimate >= 10 or file_count >= 10:
        tier = ModelTier.AUTOPILOT
    elif file_count > 5 or edit_count_estimate > 3:
        tier = ModelTier.STANDARD
    elif file_count == 1:
        tier = ModelTier.MICRO
    else:
        tier = ModelTier.TURBO

    solo = config_is_solo_mode(
        file_count, high_complexity=(tier == ModelTier.AUTOPILOT)
    )
    concurrency = config_get_concurrency_for_files(file_count)
    model = config_get_model_for_tier(tier)

    return (
        f"Suggested tier: {tier.value} ({model}). "
        f"Concurrency: {concurrency}. "
        f"Solo mode: {solo}."
    )


@router_agent.tool
async def router_list_project_helper_agents(
    ctx: RunContext[RouterDependencies],
) -> list[dict[str, object]]:
    """Return registered project-specific helper-agent specs for routing."""
    if not ctx.deps.project_root:
        return []
    try:
        from .builder.agent_builder import list_helper_agent_specs

        return [
            spec.model_dump(mode="json")
            for spec in list_helper_agent_specs(
                ctx.deps.project_root, ctx.deps.project_id
            )
        ]
    except FileNotFoundError:
        return []
