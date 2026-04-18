#!/usr/bin/env python3
# src/mem_graph/agents/fix/fixer_agent.py
"""
Fixer Agent — violation mechanic and code author.

The Mechanic. Receives a list of violations and their corresponding file
contents, proposes minimal functional logic changes to resolve each
violation, and returns the proposed diffs keyed by file path. Operates
at the caller-specified model tier for cost/intelligence scaling.
"""

from __future__ import annotations

################
#   IMPORTS
################

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from ...config import DEFER_AGENT_MODEL_CHECK, ModelTier, config_get_model_for_tier
from ...resources.personas import MECHANIC_PERSONA

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

_FIXER_MODEL = config_get_model_for_tier(ModelTier.STANDARD)

################
#   MODELS
################


class FilePatch(BaseModel):
    """
    A proposed code change for a single file.

    Attributes:
        file_path: Repo-relative path to the file being changed.
        original_snippet: The problematic code being replaced.
        proposed_snippet: The fixed code replacement.
        violation_ids: Violation IDs this patch resolves.
        rationale: Why this change fixes the violation.
    """

    file_path: str = Field(description="Repo-relative path to the target file.")
    original_snippet: str = Field(description="The exact problematic code being replaced.")
    proposed_snippet: str = Field(description="The replacement code that fixes the violation.")
    violation_ids: list[str] = Field(
        default_factory=list,
        description="Rule IDs or violation node IDs this patch resolves.",
    )
    rationale: str = Field(description="Why this change resolves the violation.")


class FixerReport(BaseModel):
    """
    Complete output from a Fixer Agent run.

    Contains all proposed patches, unresolved violations that could not
    be fixed automatically, and a summary of the proposed changes.
    """

    patches: list[FilePatch] = Field(
        default_factory=list,
        description="All proposed file patches.",
    )
    unresolved_violations: list[str] = Field(
        default_factory=list,
        description="Violation IDs that could not be automatically fixed.",
    )
    summary: str = Field(description="Narrative summary of proposed changes.")
    tier_used: str = Field(description="Model tier identifier used for this run.")


################
#   DEPS
################


@dataclass
class FixerDependencies:
    """
    Injectable dependencies for the Fixer Agent.

    Attributes:
        violations: List of violation descriptions to fix (rule:file:line:description).
        file_contents: Pre-read file content keyed by file path.
        tier: Model tier to use for this fix (from Router decision).
        project_id: Project ID for graph context.
        skills_content: Optional SKILL.md content for extra guidance.
    """

    violations: list[str]
    file_contents: dict[str, str] = field(default_factory=dict)
    tier: str = ModelTier.STANDARD.value
    project_id: str = ""
    skills_content: str = ""


################
#   AGENT
################

fixer_agent: Agent[FixerDependencies, FixerReport] = Agent(
    _FIXER_MODEL,
    name="fixer",
    deps_type=FixerDependencies,
    output_type=FixerReport,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


@fixer_agent.system_prompt
async def fixer_build_system_prompt(ctx: RunContext[FixerDependencies]) -> str:
    """
    Build the Fixer Agent system prompt.

    Injects the Mechanic persona with strict scope constraints so the
    agent never exceeds the violation-minimal change boundary.

    Args:
        ctx: The run context with FixerDependencies.

    Returns:
        Complete system prompt string.
    """
    return f"""{MECHANIC_PERSONA.get_system_instructions()}

## Scope Rules (MANDATORY)
- Fix ONLY the listed violations. Do not refactor surrounding code.
- Do not change public function signatures unless required to fix the violation.
- Do not add new dependencies — list them in your rationale for user approval.
- Every patch MUST include a rationale explaining why it resolves the violation.

## Violations to Fix
{chr(10).join(f"  - {v}" for v in ctx.deps.violations)}

## Model Tier
Operating at tier: {ctx.deps.tier}

## Tools
- Call `fixer_read_file_context` to inspect a specific file.
- Call `fixer_record_patch` for each proposed fix.
- Call `fixer_mark_unresolvable` for violations that require human review.

{ctx.deps.skills_content}
"""


@fixer_agent.tool
async def fixer_read_file_context(
    ctx: RunContext[FixerDependencies],
    file_path: str,
) -> str:
    """
    Return the pre-read content of a file for inspection.

    Args:
        ctx: The run context with FixerDependencies.
        file_path: The file path to retrieve content for.

    Returns:
        File content string or an error message if not found.
    """
    return ctx.deps.file_contents.get(file_path, f"ERROR: {file_path} not in provided context.")


@fixer_agent.tool
async def fixer_record_patch(
    ctx: RunContext[FixerDependencies],
    file_path: str,
    original_snippet: str,
    proposed_snippet: str,
    violation_ids: list[str],
    rationale: str,
) -> str:
    """
    Record a proposed file patch in the run state.

    Args:
        ctx: The run context with FixerDependencies.
        file_path: Path of the file being patched.
        original_snippet: The exact code being replaced.
        proposed_snippet: The replacement code.
        violation_ids: Violation IDs this patch resolves.
        rationale: Why this change resolves the violation.

    Returns:
        Confirmation message with patch index.
    """
    if not hasattr(ctx, "_fixer_patches"):
        ctx._fixer_patches = []  # type: ignore[attr-defined]

    patch = FilePatch(
        file_path=file_path,
        original_snippet=original_snippet,
        proposed_snippet=proposed_snippet,
        violation_ids=violation_ids,
        rationale=rationale,
    )
    ctx._fixer_patches.append(patch)  # type: ignore[attr-defined]
    logger.debug("Recorded patch %d for %s", len(ctx._fixer_patches), file_path)  # type: ignore[attr-defined]
    return f"Patch {len(ctx._fixer_patches)} recorded for `{file_path}`."  # type: ignore[attr-defined]


@fixer_agent.tool
async def fixer_mark_unresolvable(
    ctx: RunContext[FixerDependencies],
    violation_id: str,
    reason: str,
) -> str:
    """
    Mark a violation as unresolvable by automatic fix.

    Violations that require architectural changes, user decisions, or
    external dependencies should be flagged here rather than guessed at.

    Args:
        ctx: The run context with FixerDependencies.
        violation_id: The violation ID that cannot be auto-fixed.
        reason: Why automated fixing is not feasible.

    Returns:
        Confirmation that the violation was marked unresolvable.
    """
    if not hasattr(ctx, "_fixer_unresolved"):
        ctx._fixer_unresolved = []  # type: ignore[attr-defined]
    ctx._fixer_unresolved.append(f"{violation_id}: {reason}")  # type: ignore[attr-defined]
    return f"Violation {violation_id} marked as requiring human review: {reason}"
