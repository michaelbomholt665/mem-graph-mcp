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

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from ..config import (
    DEFER_AGENT_MODEL_CHECK,
    ModelTier,
    config_get_concurrency_for_files,
    config_get_model_for_tier,
    config_is_solo_mode,
)
from ..resources.personas import ROUTER_PERSONA

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

_ROUTER_MODEL = config_get_model_for_tier(ModelTier.TURBO)

################
#   MODELS
################


class RouterSubTask(BaseModel):
    """
    A single decomposed sub-task produced by the Router.

    Attributes:
        index: Execution order (0-based).
        description: What this sub-task accomplishes.
        target_files: File paths this sub-task operates on.
        agent: Which downstream agent handles this sub-task.
    """

    index: int = Field(description="Execution order index (0-based).")
    description: str = Field(description="What this sub-task accomplishes.")
    target_files: list[str] = Field(
        default_factory=list,
        description="File paths this sub-task operates on.",
    )
    agent: str = Field(
        description="Downstream agent: audit, fixer, scribe, validation, map, decision.",
    )


class RouterDecision(BaseModel):
    """
    Classification and decomposition result from the Router Agent.

    Encodes the selected tier, concurrency recommendation, and ordered
    sub-task list for execution by the Autopilot workflow.
    """

    tier: ModelTier = Field(description="Selected model tier for downstream agents.")
    file_count: int = Field(description="Total files involved in this request.")
    concurrency: int = Field(description="Recommended parallel worker count.")
    solo_mode: bool = Field(
        default=False,
        description="True when Autopilot tier should process full context without batching.",
    )
    intent: str = Field(
        description="Detected intent: audit, fix, map, refactor, document, review.",
    )
    summary: str = Field(description="One-line summary of what will be done and why.")
    sub_tasks: list[RouterSubTask] = Field(
        default_factory=list,
        description="Ordered sub-tasks for the downstream pipeline.",
    )


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


################
#   AGENT
################

router_agent: Agent[RouterDependencies, RouterDecision] = Agent(
    _ROUTER_MODEL,
    name="router",
    deps_type=RouterDependencies,
    output_type=RouterDecision,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


@router_agent.system_prompt
async def router_build_system_prompt(ctx: RunContext[RouterDependencies]) -> str:
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

    return f"""{ROUTER_PERSONA.get_system_instructions()}

## Your Task
Classify the incoming request, select the appropriate model tier, and
decompose the work into ordered sub-tasks.

## File Scope
{file_count} file(s) in scope. Recommended concurrency: {concurrency} worker(s).

## Open Violations (graph context)
{chr(10).join(ctx.deps.context_violations[:20]) or 'None'}

## Active Decisions (graph context)
{chr(10).join(ctx.deps.context_decisions[:10]) or 'None'}

## Tier Selection Rules
- TURBO: Classification, pattern matching, simple single-file queries.
- MICRO: Single-file edits, typo fixes, docstring additions.
- STANDARD: Multi-file audits, task decomposition, mapping (default).
- AUTOPILOT: 10+ edits, 10+ new files, deep debugging, full refactors.

## Output Requirements
Return a RouterDecision with tier, file_count, concurrency, solo_mode,
intent, summary, and a sub_tasks list ordered by execution dependency.

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

    solo = config_is_solo_mode(file_count, high_complexity=(tier == ModelTier.AUTOPILOT))
    concurrency = config_get_concurrency_for_files(file_count)
    model = config_get_model_for_tier(tier)

    return (
        f"Suggested tier: {tier.value} ({model}). "
        f"Concurrency: {concurrency}. "
        f"Solo mode: {solo}."
    )
