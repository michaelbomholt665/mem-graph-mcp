#!/usr/bin/env python3
# src/mem_graph/agents/document/decision_agent.py
"""
Decision review agent.

Periodically checks architectural decisions stored in the graph against
the current codebase and flags decisions that have drifted from reality.
Accepts injected decisions and file snapshots — does not read the graph
directly, keeping it testable and transport-agnostic.

Agent-local tools: list_files, process_batch, finalize_review
"""

from __future__ import annotations

################
#   IMPORTS
################

from dataclasses import dataclass, field
from enum import Enum
import logging
import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from ...config import AGENT_MODEL, DEFER_AGENT_MODEL_CHECK, config_model_settings
from ...resources.personas import ARCHITECT_PERSONA
from ...resources.prompts import get_reasoning_mode_guidance

################
#   CONSTANTS
################

_MAX_FILE_BYTES = 64_000

logger = logging.getLogger(__name__)


################
#   MODELS
################


class DriftStatus(str, Enum):
    """
    Whether a decision is still reflected in the codebase.

    HONOURED: code matches the decision's intent.
    DRIFTED: code has diverged from what the decision specified.
    SUPERSEDED: decision was already marked superseded in the graph.
    UNVERIFIABLE: not enough code evidence to make a determination.
    """

    HONOURED = "honoured"
    DRIFTED = "drifted"
    SUPERSEDED = "superseded"
    UNVERIFIABLE = "unverifiable"


class DecisionReview(BaseModel):
    """
    Review outcome for a single architectural decision.

    Produced by the agent after comparing the decision's rationale
    against current source files.
    """

    decision_id: str = Field(description="Graph decision ID being reviewed.")
    decision_title: str = Field(description="Human-readable decision title.")
    status: DriftStatus = Field(description="Whether the decision is still honoured.")
    evidence: str = Field(
        description="Specific code evidence supporting the drift assessment."
    )
    drifted_files: list[str] = Field(
        default_factory=list,
        description="Files where the drift is visible.",
    )
    recommendation: str = Field(
        description=(
            "What to do: 'no action', 'update decision', 'fix code', "
            "'open violation', or 'supersede decision'."
        )
    )
    severity: str = Field(
        default="minor",
        description="How serious the drift is: 'info', 'minor', 'major', 'critical'.",
    )


class ReviewReport(BaseModel):
    """
    Complete decision review for a project.

    Contains all individual decision reviews and a summary of
    how many decisions are still being honoured vs drifted.
    """

    project_id: str = Field(description="Project this review belongs to.")
    reviews: list[DecisionReview] = Field(default_factory=list)
    summary: str = Field(description="Narrative overview of the review findings.")
    honoured_count: int = Field(default=0)
    drifted_count: int = Field(default=0)
    unverifiable_count: int = Field(default=0)
    partial_failure: bool = Field(default=False)


################
#   DEPS
################


@dataclass
class DecisionDependencies:
    """
    Injectable dependencies for the decision review agent.

    decisions: serialised Decision nodes from the graph to review.
    package_path: root directory to read source files from.
    project_id: for output linkage.
    skills_content: optional domain knowledge.
    _decision_state: accumulated DecisionReview objects across tool calls;
        never monkey-patched onto RunContext.
    """

    project_id: str
    package_path: str
    decisions: list[dict] = field(default_factory=list)
    skills_content: str = ""
    extra_file_context: str = ""
    _decision_state: list["DecisionReview"] = field(default_factory=list)
    reasoning_mode: str = ""

################
#   AGENT
################

decision_agent: Agent[DecisionDependencies, ReviewReport] = Agent(
    AGENT_MODEL,
    name="decision",
    deps_type=DecisionDependencies,
    output_type=ReviewReport,
    model_settings=config_model_settings(
        temperature=ARCHITECT_PERSONA.params.temperature,
        top_p=ARCHITECT_PERSONA.params.top_p,
    ),
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


################
#   PROMPTS
################


@decision_agent.system_prompt
async def build_system_prompt(ctx: RunContext[DecisionDependencies]) -> str:
    """
    Build the system prompt from deps and the Architect persona at runtime.
    """
    persona_instr = ARCHITECT_PERSONA.get_system_instructions()
    skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."
    decisions_block = _format_decisions(ctx.deps.decisions)

    reasoning_hint = ""
    if ctx.deps.reasoning_mode:
        reasoning_hint = (
            f"\n\n## Reasoning Strategy\n"
            f"{get_reasoning_mode_guidance(ctx.deps.reasoning_mode)}"
        )

    if ctx.deps.extra_file_context:
        file_section = (
            "## Pre-loaded Files\n"
            f"{ctx.deps.extra_file_context}\n\n"
            "The files above were pre-loaded by the orchestrator."
        )
        workflow = """1. Review the supplied decisions against only the pre-loaded files shown above.
2. Return the final ReviewReport directly as structured output.
3. Do not call list_files, process_batch, or finalize_review."""
        analysis_scope = "the pre-loaded files"
    else:
        file_section = ""
        workflow = """1. Call `list_files` to retrieve the package source file paths.
2. Call `process_batch` iteratively. Pass up to 5 `file_paths` to inspect, along with `reviews_from_previous_batch` (empty on the first call).
3. The tool returns the file contents. Evaluate the specific decisions against these files.
4. Call `process_batch` again with your completed `DecisionReview` objects for any decisions you have fully assessed, requesting the next batch of files if needed.
5. After evaluating all decisions, call `process_batch` with an empty `file_paths` list to submit your final reviews.
6. Call `finalize_review` with a summary of the outcomes."""
        analysis_scope = ctx.deps.package_path

    return f"""{persona_instr}

## Domain Knowledge
{skills_block}

{file_section}

## Decisions to Review
{decisions_block}

## Package to Inspect
{analysis_scope}

## Your Task
{workflow}

## Assessment Criteria
- HONOURED: You can point to code that implements or respects the decision.
- DRIFTED: You can point to code that contradicts or ignores the decision.
- SUPERSEDED: The decision is already marked superseded — confirm and note.
- UNVERIFIABLE: The decision is about process or tooling, not inspectable in source.

## Evidence Standards
- Always cite specific files and describe what you saw.
- Do not mark DRIFTED without naming the file and what the violation is.
- Do not mark HONOURED just because you found no violations — look for positive evidence.
- Trivial drift (naming, style) is 'minor'. Architectural violations are 'major' or 'critical'.
{reasoning_hint}
"""


def _format_decisions(decisions: list[dict]) -> str:
    """Render decisions as a numbered review list."""
    if not decisions:
        return "No decisions provided — nothing to review."

    lines = []
    for i, d in enumerate(decisions, 1):
        lines.append(
            f"{i}. [{d.get('id', '?')}] {d.get('title', '?')} "
            f"(status={d.get('status', '?')}, impact={d.get('impact', '?')})\n"
            f"   Rationale: {d.get('rationale', '')[:200]}\n"
            f"   Alternatives rejected: {d.get('alternatives', 'none recorded')[:100]}"
        )
    return "\n\n".join(lines)


################
#   TOOLS
################


@decision_agent.tool  # Scope: agent-local only
async def list_files(
    ctx: RunContext[DecisionDependencies],
    extension: str = ".py",
) -> list[str]:
    """
    List source files in the package directory.

    Used by the agent to discover which files to read when
    checking whether a decision is reflected in the code.
    """
    import glob

    pattern = os.path.join(ctx.deps.package_path, f"**/*{extension}")
    return glob.glob(pattern, recursive=True)


@decision_agent.tool  # Scope: agent-local only
async def process_batch(
    ctx: RunContext[DecisionDependencies],
    file_paths: list[str],
    reviews_from_previous_batch: list[DecisionReview],
) -> str:
    """
    Submit decision reviews and receive the next batch of file content to inspect.

    Pass an empty list for reviews_from_previous_batch on the first call.
    Max 5 files requested at once. The returned file content informs your 
    ensuing reviews.
    """
    _get_state(ctx).extend(reviews_from_previous_batch)

    results = []
    for path in file_paths[:5]:
        content = _read_file_internal(path)
        results.append(f"### {path}\n{content}")

    if not results:
        return "No files requested. Reviews stored."

    return "\n\n".join(results)


def _read_file_internal(file_path: str) -> str:
    """Internal helper to read file content robustly."""
    if not os.path.exists(file_path):
        return f"ERROR:NOT_FOUND:{file_path}"

    try:
        raw = Path(file_path).read_bytes()
    except Exception as exc:
        return f"ERROR:READ_FAILED:{exc}"

    if len(raw) > _MAX_FILE_BYTES:
        truncated = raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
        return truncated + f"\n\n[TRUNCATED — file exceeds {_MAX_FILE_BYTES} bytes]"

    return raw.decode("utf-8", errors="replace")


@decision_agent.tool  # Scope: agent-local only
async def finalize_review(
    ctx: RunContext[DecisionDependencies],
    summary: str,
    partial_failure: bool = False,
) -> ReviewReport:
    """
    Aggregate all decision reviews into the final ReviewReport.

    Called once after all decisions have been assessed.
    Computes summary counts from recorded reviews.
    """
    reviews = _get_state(ctx)
    counts = _compute_counts(reviews)

    return ReviewReport(
        project_id=ctx.deps.project_id,
        reviews=reviews,
        summary=summary,
        partial_failure=partial_failure,
        **counts,
    )


################
#   HELPERS
################


def _get_state(ctx: RunContext[DecisionDependencies]) -> list[DecisionReview]:
    """Retrieve the per-run review accumulator from deps (never monkey-patched)."""
    return ctx.deps._decision_state


def _compute_counts(reviews: list[DecisionReview]) -> dict:
    """Compute summary counts from a list of decision reviews."""
    return {
        "honoured_count": sum(1 for r in reviews if r.status == DriftStatus.HONOURED),
        "drifted_count": sum(1 for r in reviews if r.status == DriftStatus.DRIFTED),
        "unverifiable_count": sum(1 for r in reviews if r.status == DriftStatus.UNVERIFIABLE),
    }
