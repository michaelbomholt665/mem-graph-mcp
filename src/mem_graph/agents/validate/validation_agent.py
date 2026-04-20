#!/usr/bin/env python3
# src/mem_graph/agents/validate/validation_agent.py
"""
Validation Agent — post-fix quality gate.

The Guard. Receives the proposed patches from Fixer and Scribe, runs a
mini-audit for logic and style regressions, and returns an approve/reject
decision with detailed violation feedback for the retry loop.
"""

from __future__ import annotations

################
#   IMPORTS
################
import logging
from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext

from ...config import DEFER_AGENT_MODEL_CHECK, ModelTier, config_get_model_for_tier
from ...models.agent_outputs import (
    ValidationCheck,
    ValidationReport,
    ValidationSeverity,
    ValidationStatus,
    ValidationViolation,
)
from ...resources.coding_standards import coding_standards_get_for_language
from ...resources.personas import GUARD_PERSONA
from ...resources.prompts import (
    build_tool_names_for_prompt,
    get_reasoning_mode_guidance,
)

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

_VALIDATION_MODEL = config_get_model_for_tier(ModelTier.STANDARD)

################
#   DEPS
################


@dataclass
class ValidationDependencies:
    """
    Injectable dependencies for the Validation Agent.

    Attributes:
        language: Target language for standards enforcement.
        original_violations: Violations that the Fixer was asked to resolve.
        proposed_patches: File content after Fixer + Scribe passes, keyed by path.
        original_file_contents: File content before any changes, keyed by path.
        skills_content: Optional SKILL.md content for extra guidance.
        _validation_violations: Accumulated ValidationViolation objects;
            never monkey-patched onto RunContext.
    """

    language: str
    original_violations: list[str]
    proposed_patches: dict[str, str] = field(default_factory=dict)
    original_file_contents: dict[str, str] = field(default_factory=dict)
    skills_content: str = ""
    _validation_violations: list[ValidationViolation] = field(default_factory=list)
    reasoning_mode: str = ""


################
#   AGENT
################

validation_agent: Agent[ValidationDependencies, ValidationReport] = Agent(
    _VALIDATION_MODEL,
    name="validator",
    deps_type=ValidationDependencies,
    output_type=ValidationReport,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


@validation_agent.instructions
async def validation_build_instructions(ctx: RunContext[ValidationDependencies]) -> str:
    """
    Build the Validation Agent system prompt.

    Injects the Guard persona with the full reject criteria and standards
    block so the agent applies the same rules Scribe enforced.

    Args:
        ctx: The run context with ValidationDependencies.

    Returns:
        Complete system prompt string.
    """
    standards = coding_standards_get_for_language(ctx.deps.language)

    reasoning_hint = ""
    if ctx.deps.reasoning_mode:
        reasoning_hint = (
            f"\n\n## Reasoning Strategy\n"
            f"{get_reasoning_mode_guidance(ctx.deps.reasoning_mode)}"
        )

    tools_section = build_tool_names_for_prompt(
        [
            "validation_inspect_patch",
            "validation_record_violation",
            "validation_finalize_decision",
        ]
    )

    return f"""{GUARD_PERSONA.get_system_instructions()}

## Language Standards Being Enforced
{standards}

## Original Violations (must all be resolved)
{chr(10).join(f"  - {v}" for v in ctx.deps.original_violations)}

## Reject Conditions (ANY one is sufficient to reject)
1. A violation from the original list is NOT resolved by the patch.
2. The patch introduces a NEW logic violation not present in the original.
3. Required documentation (shebang, path header, docstrings) is missing.
4. Naming convention violations exist (2-3 token rule, feature prefix).
5. Scope was exceeded — functional code changed beyond the violation scope.
{tools_section}{reasoning_hint}

{ctx.deps.skills_content}
"""


@validation_agent.tool  # Scope: agent-local only
async def validation_inspect_patch(
    ctx: RunContext[ValidationDependencies],
    file_path: str,
) -> dict:
    """
    Return both the original and proposed content for a file.

    Allows the Guard to perform a side-by-side comparison to detect
    scope violations and check that all original violations are resolved.

    Args:
        ctx: The run context with ValidationDependencies.
        file_path: The file to inspect.

    Returns:
        Dict with 'original' and 'proposed' content strings.
    """
    return {
        "original": ctx.deps.original_file_contents.get(file_path, "NOT AVAILABLE"),
        "proposed": ctx.deps.proposed_patches.get(file_path, "NOT AVAILABLE"),
    }


@validation_agent.tool  # Scope: agent-local only
async def validation_record_violation(
    ctx: RunContext[ValidationDependencies],
    file_path: str,
    check: ValidationCheck,
    description: str,
    severity: ValidationSeverity,
) -> str:
    """
    Record a validation issue found during patch inspection.

    Args:
        ctx: The run context with ValidationDependencies.
        file_path: File where the issue was found.
        check: Which check failed (logic, style, naming, scope_exceeded).
        description: What is wrong and what must be corrected.
        severity: How critical — critical, major, minor.

    Returns:
        Confirmation that the violation was recorded.
    """
    v = ValidationViolation(
        file_path=file_path, check=check, description=description, severity=severity
    )
    ctx.deps._validation_violations.append(v)
    logger.debug(
        "Validation issue recorded: [%s] %s — %s", check, file_path, description
    )
    return f"Issue recorded ({check}/{severity}) for `{file_path}`."


@validation_agent.tool  # Scope: agent-local only
async def validation_finalize_decision(
    ctx: RunContext[ValidationDependencies],
    rationale: str,
) -> ValidationReport:
    """
    Finalise the approve/reject decision and produce the ValidationReport.

    Decision is APPROVED only when no violations were recorded. The
    caller (orchestrator_graph) uses this to route to MemorySync or retry.

    Args:
        ctx: The run context with ValidationDependencies.
        rationale: Detailed explanation of the decision.

    Returns:
        The completed ValidationReport with status and violations.
    """
    recorded = ctx.deps._validation_violations
    status = ValidationStatus.APPROVED if not recorded else ValidationStatus.REJECTED

    logger.info(
        "Validation %s: %d issue(s) across %d file(s).",
        status.value,
        len(recorded),
        len(ctx.deps.proposed_patches),
    )

    return ValidationReport(
        status=status,
        violations=recorded,
        rationale=rationale,
        files_checked=len(ctx.deps.proposed_patches),
    )
