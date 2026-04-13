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
from enum import Enum

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from ...config import DEFER_AGENT_MODEL_CHECK, ModelTier, config_get_model_for_tier
from ...resources.coding_standards import coding_standards_get_for_language
from ...resources.personas import GUARD_PERSONA

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

_VALIDATION_MODEL = config_get_model_for_tier(ModelTier.STANDARD)

################
#   MODELS
################


class ValidationStatus(str, Enum):
    """
    Result of the validation gate.

    APPROVED means the patch is safe to apply and sync to the graph.
    REJECTED means one or more checks failed — the patch must be revised.
    """

    APPROVED = "approved"
    REJECTED = "rejected"


class ValidationViolation(BaseModel):
    """
    A single issue found during validation of a proposed patch.

    Attributes:
        file_path: File where the issue was detected.
        check: Which validation check failed.
        description: What is wrong with the proposed change.
        severity: How critical this finding is for the approve/reject decision.
    """

    file_path: str = Field(description="File where the issue was detected.")
    check: str = Field(
        description="Check that failed: 'logic', 'style', 'naming', 'scope_exceeded'.",
    )
    description: str = Field(description="What is wrong and what must be corrected.")
    severity: str = Field(
        default="major",
        description="Severity: critical, major, minor.",
    )


class ValidationReport(BaseModel):
    """
    Complete output from a Validation Agent run.

    Contains the approve/reject decision, all validation violations found,
    and a detailed rationale for the decision.
    """

    status: ValidationStatus = Field(description="APPROVED or REJECTED.")
    violations: list[ValidationViolation] = Field(
        default_factory=list,
        description="Issues found during validation (empty when APPROVED).",
    )
    rationale: str = Field(description="Detailed explanation of the decision.")
    files_checked: int = Field(description="Number of patch files inspected.")


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
    """

    language: str
    original_violations: list[str]
    proposed_patches: dict[str, str] = field(default_factory=dict)
    original_file_contents: dict[str, str] = field(default_factory=dict)
    skills_content: str = ""


################
#   AGENT
################

validation_agent: Agent[ValidationDependencies, ValidationReport] = Agent(
    _VALIDATION_MODEL,
    deps_type=ValidationDependencies,
    output_type=ValidationReport,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


@validation_agent.system_prompt
async def validation_build_system_prompt(ctx: RunContext[ValidationDependencies]) -> str:
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

## Tools
- Call `validation_inspect_patch` to compare original vs proposed content.
- Call `validation_record_violation` for each issue found.
- Call `validation_finalize_decision` to issue the approve/reject verdict.

{ctx.deps.skills_content}
"""


@validation_agent.tool
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


@validation_agent.tool
async def validation_record_violation(
    ctx: RunContext[ValidationDependencies],
    file_path: str,
    check: str,
    description: str,
    severity: str,
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
    if not hasattr(ctx, "_validation_violations"):
        ctx._validation_violations = []  # type: ignore[attr-defined]

    v = ValidationViolation(
        file_path=file_path, check=check, description=description, severity=severity
    )
    ctx._validation_violations.append(v)  # type: ignore[attr-defined]
    logger.debug("Validation issue recorded: [%s] %s — %s", check, file_path, description)
    return f"Issue recorded ({check}/{severity}) for `{file_path}`."


@validation_agent.tool
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
    recorded = getattr(ctx, "_validation_violations", [])
    status = (
        ValidationStatus.APPROVED if not recorded else ValidationStatus.REJECTED
    )

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
