#!/usr/bin/env python3
# src/mem_graph/agents/document/task_agent.py
"""
Task decomposition agent.

Takes a feature description, queries injected graph context for relevant
codebase knowledge (file locations, open violations, prior decisions),
and produces a sequenced task list with explicit dependencies. Designed
to be fed MapReport output from the map agent for codebase awareness.

Agent-local tools: process_batch, finalize_decomposition
"""

from __future__ import annotations

################
#   IMPORTS
################
import logging
from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext

from ...capabilities import ReasoningStrategyCapability
from ...config import AGENT_MODEL, DEFER_AGENT_MODEL_CHECK, config_model_settings
from ...models.agent_outputs import DecompositionReport, Task, TaskComplexity
from ...resources.personas import ARCHITECT_PERSONA

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)


################
#   DEPS
################


@dataclass
class TaskDependencies:
    """
    Injectable dependencies for the task decomposition agent.

    feature_description: what needs to be built.
    project_id: for graph context linkage.
    codebase_map: serialised MapReport features for file awareness.
    open_violations: relevant open violations from the graph.
    prior_decisions: decisions from the graph that constrain the work.
    skills_content: optional domain knowledge.
    _task_state: accumulated Task objects across tool calls;
        never monkey-patched onto RunContext.
    """

    feature_description: str
    project_id: str
    codebase_map: list[dict] = field(default_factory=list)
    open_violations: list[dict] = field(default_factory=list)
    prior_decisions: list[dict] = field(default_factory=list)
    skills_content: str = ""
    _task_state: list["Task"] = field(default_factory=list)
    reasoning_mode: str = ""


################
#   AGENT
################

task_agent: Agent[TaskDependencies, DecompositionReport] = Agent(
    AGENT_MODEL,
    name="task-decomposer",
    deps_type=TaskDependencies,
    output_type=DecompositionReport,
    model_settings=config_model_settings(
        temperature=ARCHITECT_PERSONA.params.temperature,
        top_p=ARCHITECT_PERSONA.params.top_p,
    ),
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
    capabilities=[ReasoningStrategyCapability()],
)


################
#   PROMPTS
################


@task_agent.instructions
async def build_instructions(ctx: RunContext[TaskDependencies]) -> str:
    """
    Build the system prompt from deps and the Architect persona at runtime.
    """
    persona_instr = ARCHITECT_PERSONA.get_system_instructions()
    skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."
    map_block = _format_codebase_map(ctx.deps.codebase_map)
    violations_block = _format_violations(ctx.deps.open_violations)
    decisions_block = _format_decisions(ctx.deps.prior_decisions)

    return f"""{persona_instr}

## Domain Knowledge
{skills_block}

## Feature Request
{ctx.deps.feature_description}

## Codebase Map (what lives where)
{map_block}

## Open Violations (constraints and risks)
{violations_block}

## Prior Decisions (architectural constraints)
{decisions_block}

## Your Task
1. Call `process_batch` iteratively. Submit generated tasks (if any) and optionally ask context queries about the codebase map or graph data.
2. The tool will return answers to your context queries (if provided).
3. Ensure every task has a clear phase (planning -> red -> green -> refactor -> audit).
4. Wire dependencies explicitly — a task that touches a file another task creates must depend on it.
5. Link relevant open violations and decisions to the tasks that address or are constrained by them.
6. Once decomposed, call `process_batch` with an empty queries list to save your remaining tasks, then call `finalize_decomposition` with identified blockers and complexity estimate.

## Task Quality Rules
- Each task should be completable in one focused session.
- acceptance_criteria must be specific and verifiable — not 'works correctly'.
- If an open violation affects a file this feature touches, link it to the relevant task.
- If a prior decision constrains the implementation, reference it and honour it.
- Do not create tasks that contradict prior decisions without flagging the conflict.
- Phase ordering: planning tasks before red, red before green, green before refactor.
"""


def _format_codebase_map(features: list[dict]) -> str:
    """Render codebase map features as a reference list."""
    if not features:
        return (
            "No codebase map available — decompose based on feature description alone."
        )

    lines = []
    for f in features:
        consumers = ", ".join(f.get("consumers", []))
        lines.append(
            f"- {f.get('feature_name', '?')}: {f.get('primary_file', '?')}"
            + (f" | consumed by: {consumers}" if consumers else "")
        )
    return "\n".join(lines)


def _format_violations(violations: list[dict]) -> str:
    """Render open violations as a reference list."""
    if not violations:
        return "No open violations in this area."

    lines = []
    for v in violations:
        lines.append(
            f"- [{v.get('id', '?')}] {v.get('rule', '?')} "
            f"{v.get('file_path', '?')} ({v.get('severity', '?')}): "
            f"{v.get('description', '')[:120]}"
        )
    return "\n".join(lines)


def _format_decisions(decisions: list[dict]) -> str:
    """Render prior architectural decisions as a reference list."""
    if not decisions:
        return "No prior decisions recorded for this project."

    lines = []
    for d in decisions:
        lines.append(
            f"- [{d.get('id', '?')}] {d.get('title', '?')}: "
            f"{d.get('rationale', '')[:150]}"
        )
    return "\n".join(lines)


################
#   TOOLS
################


@task_agent.tool  # Scope: agent-local only
async def process_batch(
    ctx: RunContext[TaskDependencies],
    context_queries: list[str],
    tasks_from_previous_batch: list[Task],
) -> str:
    """
    Submit tasks generated in the previous step and optionally retrieve answers
    to queries about the graph context.

    Request answers to at most 5 context questions at once. Pass an empty
    context_queries list to just submit tasks.
    """
    _get_state(ctx).extend(tasks_from_previous_batch)

    results = []
    for q in context_queries[:5]:
        results.append(
            f"### Query: {q}\n"
            f"[Context query stub] Cannot dynamically graph search yet. "
            "Please rely on the injected map/violations/decisions."
        )

    if not results:
        return "No context queries requested. Tasks stored."

    return "\n\n".join(results)


@task_agent.tool  # Scope: agent-local only
async def finalize_decomposition(
    ctx: RunContext[TaskDependencies],
    summary: str,
    identified_blockers: list[str],
    estimated_complexity: TaskComplexity = "medium",
    partial_failure: bool = False,
) -> DecompositionReport:
    """
    Aggregate all recorded tasks into the final DecompositionReport.

    Called once after all tasks have been recorded and dependencies wired.
    """
    return DecompositionReport(
        feature_description=ctx.deps.feature_description,
        project_id=ctx.deps.project_id,
        tasks=_get_state(ctx),
        summary=summary,
        identified_blockers=identified_blockers,
        estimated_complexity=estimated_complexity,
        partial_failure=partial_failure,
    )


################
#   HELPERS
################


def _get_state(ctx: RunContext[TaskDependencies]) -> list[Task]:
    """Retrieve the per-run task accumulator from deps (never monkey-patched)."""
    return ctx.deps._task_state
