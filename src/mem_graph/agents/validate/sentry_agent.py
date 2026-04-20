#!/usr/bin/env python3
# src/mem_graph/agents/validate/sentry_agent.py
"""
Sentry Agent — test architect for red-first validation.

The Sentry writes failing tests before the Mechanic changes production code.
It focuses on minimal, deterministic test coverage that proves the bug or
missing behavior before any fix is attempted.

Agent-local tools: sentry_read_file, sentry_record_test, sentry_finalize_plan
"""

from __future__ import annotations

################
#   IMPORTS
################
import logging
from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext

from ...config import DEFER_AGENT_MODEL_CHECK, ModelTier, config_get_model_for_tier
from ...models.agent_outputs import SentryReport, TestCaseProposal
from ...resources.coding_standards import coding_standards_get_for_language
from ...resources.personas import SENTRY_PERSONA
from ...resources.prompts import (
    build_tool_names_for_prompt,
    get_reasoning_mode_guidance,
)

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

_SENTRY_MODEL = config_get_model_for_tier(ModelTier.MICRO)

################
#   DEPS
################


@dataclass
class SentryDependencies:
    """Injectable dependencies for the Sentry Agent."""

    language: str
    file_contents: dict[str, str] = field(default_factory=dict)
    manifest_context: dict[str, str] = field(default_factory=dict)
    context_violations: list[str] = field(default_factory=list)
    context_decisions: list[str] = field(default_factory=list)
    skills_content: str = ""
    _sentry_tests: list[TestCaseProposal] = field(default_factory=list)
    reasoning_mode: str = ""


################
#   AGENT
################

sentry_agent: Agent[SentryDependencies, SentryReport] = Agent(
    _SENTRY_MODEL,
    name="sentry",
    deps_type=SentryDependencies,
    output_type=SentryReport,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


@sentry_agent.instructions
async def sentry_build_instructions(ctx: RunContext[SentryDependencies]) -> str:
    """Build the Sentry Agent system prompt."""
    standards = coding_standards_get_for_language(ctx.deps.language)
    manifest_block = "\n".join(
        f"- {path}:\n{content}" for path, content in ctx.deps.manifest_context.items()
    )

    reasoning_hint = ""
    if ctx.deps.reasoning_mode:
        reasoning_hint = (
            f"\n\n## Reasoning Strategy\n"
            f"{get_reasoning_mode_guidance(ctx.deps.reasoning_mode)}"
        )

    tools_section = build_tool_names_for_prompt(
        ["sentry_read_file", "sentry_record_test", "sentry_finalize_plan"]
    )

    return f"""{SENTRY_PERSONA.get_system_instructions()}

## Language Standards Being Enforced
{standards}

## Manifest Context
{manifest_block or "None provided."}

## Existing Violations (must be covered by red tests)
{chr(10).join(f"  - {violation}" for violation in ctx.deps.context_violations) or "  - None"}

## Existing Decisions (respect these when writing tests)
{chr(10).join(f"  - {decision}" for decision in ctx.deps.context_decisions) or "  - None"}

## Test Architecture Rules
- Draft the failing test first; do not propose production changes here.
- Keep the tests deterministic and minimal.
- Prefer existing framework conventions in the repository.
- Focus on the bug or gap that must fail before the fix is applied.
{tools_section}{reasoning_hint}

{ctx.deps.skills_content}
"""


@sentry_agent.tool  # Scope: agent-local only
async def sentry_read_file(
    ctx: RunContext[SentryDependencies],
    file_path: str,
) -> str:
    """Return the pre-read content of a file for inspection."""
    return ctx.deps.file_contents.get(
        file_path, f"ERROR: {file_path} not in provided context."
    )


@sentry_agent.tool  # Scope: agent-local only
async def sentry_record_test(
    ctx: RunContext[SentryDependencies],
    file_path: str,
    test_name: str,
    failing_assertion: str,
    rationale: str,
) -> str:
    """Record a proposed failing test in the run state."""
    proposal = TestCaseProposal(
        file_path=file_path,
        test_name=test_name,
        failing_assertion=failing_assertion,
        rationale=rationale,
    )
    ctx.deps._sentry_tests.append(proposal)
    logger.debug("Recorded Sentry test %s for %s", test_name, file_path)
    return f"Test proposal recorded for `{file_path}`: {test_name}."


@sentry_agent.tool  # Scope: agent-local only
async def sentry_finalize_plan(
    ctx: RunContext[SentryDependencies],
    summary: str,
    framework: str,
) -> SentryReport:
    """Finalize the failing-test plan and produce the SentryReport."""
    test_cases = ctx.deps._sentry_tests
    logger.info(
        "Sentry planned %d test case(s) for %d file(s).",
        len(test_cases),
        len(ctx.deps.file_contents),
    )

    return SentryReport(
        test_cases=test_cases,
        summary=summary,
        framework=framework,
    )
