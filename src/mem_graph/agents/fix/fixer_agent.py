#!/usr/bin/env python3
# src/mem_graph/agents/fix/fixer_agent.py
"""
Fixer Agent — violation mechanic and code author.

The Mechanic. Receives a list of violations and their corresponding file
contents, proposes minimal functional logic changes to resolve each
violation, and returns the proposed diffs keyed by file path. Operates
at the caller-specified model tier for cost/intelligence scaling.

Agent-local tools: fixer_read_file_context, fixer_record_patch, fixer_mark_unresolvable
"""

from __future__ import annotations

################
#   IMPORTS
################
import logging
from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext

from ...config import DEFER_AGENT_MODEL_CHECK, ModelTier, config_get_model_for_tier
from ...models.agent_outputs import FilePatch, FixerReport
from ...resources.personas import MECHANIC_PERSONA
from ...resources.prompts import (
    build_tool_names_for_prompt,
    get_reasoning_mode_guidance,
)

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

_FIXER_MODEL = config_get_model_for_tier(ModelTier.STANDARD)

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
        _fixer_patches: Accumulated FilePatch objects recorded during the run;
            never monkey-patched onto RunContext.
        _fixer_unresolved: Violation IDs that could not be auto-fixed;
            never monkey-patched onto RunContext.
    """

    violations: list[str]
    file_contents: dict[str, str] = field(default_factory=dict)
    tier: str = ModelTier.STANDARD.value
    project_id: str = ""
    skills_content: str = ""
    _fixer_patches: list[FilePatch] = field(default_factory=list)
    _fixer_unresolved: list[str] = field(default_factory=list)
    reasoning_mode: str = ""


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


@fixer_agent.instructions
async def fixer_build_instructions(ctx: RunContext[FixerDependencies]) -> str:
    """
    Build the Fixer Agent system prompt.

    Injects the Mechanic persona with strict scope constraints so the
    agent never exceeds the violation-minimal change boundary.

    Args:
        ctx: The run context with FixerDependencies.

    Returns:
        Complete system prompt string.
    """
    reasoning_hint = ""
    if ctx.deps.reasoning_mode:
        reasoning_hint = (
            f"\n\n## Reasoning Strategy\n"
            f"{get_reasoning_mode_guidance(ctx.deps.reasoning_mode)}"
        )

    tools_section = build_tool_names_for_prompt(
        ["fixer_read_file_context", "fixer_record_patch", "fixer_mark_unresolvable"]
    )

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
{tools_section}{reasoning_hint}

{ctx.deps.skills_content}
"""


@fixer_agent.tool  # Scope: agent-local only
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
    return ctx.deps.file_contents.get(
        file_path, f"ERROR: {file_path} not in provided context."
    )


@fixer_agent.tool  # Scope: agent-local only
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
    patch = FilePatch(
        file_path=file_path,
        original_snippet=original_snippet,
        proposed_snippet=proposed_snippet,
        violation_ids=violation_ids,
        rationale=rationale,
    )
    ctx.deps._fixer_patches.append(patch)
    logger.debug("Recorded patch %d for %s", len(ctx.deps._fixer_patches), file_path)
    return f"Patch {len(ctx.deps._fixer_patches)} recorded for `{file_path}`."


@fixer_agent.tool  # Scope: agent-local only
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
    ctx.deps._fixer_unresolved.append(f"{violation_id}: {reason}")
    return f"Violation {violation_id} marked as requiring human review: {reason}"
