#!/usr/bin/env python3
# src/mem_graph/agents/audit/audit_agent.py
"""
Generic code audit agent.

Analyses source files for bugs, leaks, silent errors, security issues,
and missing implementations. Accepts injectable AuditRule lists so the
same agent can serve as a general-purpose auditor or be specialised for
a specific domain (e.g. lakehouse invariants) without subclassing.

Produces a structured AuditReport consumed by report_writer and
violation_writer downstream.
"""

from __future__ import annotations

################
#   IMPORTS
################

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

import anyio
from pydantic_ai import Agent, RunContext

from ...config import AGENT_MODEL, DEFER_AGENT_MODEL_CHECK, config_model_settings
from ...models.audit import (
    AuditReport,
    AuditRule,
    AuditStats,
    FileAuditResult,
    FindingCategory,
    Severity,
)
from ...resources.personas import AUDITOR_PERSONA
from .rules import DEFAULT_RULES

################
#   CONSTANTS
################

_MAX_FILE_BYTES = 64_000
_RETRY_MAX = 3

logger = logging.getLogger(__name__)

################
#   DEPS
################


@dataclass
class AuditDependencies:
    """
    Injectable dependencies for the audit agent.

    Separates configuration from agent logic. Pass domain-specific
    rules to specialise the agent without modifying it.
    """

    package_path: str
    rules: list[AuditRule] = field(default_factory=lambda: list(DEFAULT_RULES))
    file_extension: str = ".py"
    skills_content: str = ""
    extra_file_context: str = ""
    file_results: list[FileAuditResult] = field(default_factory=list)

################
#   AGENT
################

audit_agent: Agent[AuditDependencies, AuditReport] = Agent(
    AGENT_MODEL,
    name="audit",
    deps_type=AuditDependencies,
    output_type=AuditReport,
    model_settings=config_model_settings(
        temperature=AUDITOR_PERSONA.params.temperature,
        top_p=AUDITOR_PERSONA.params.top_p,
    ),
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)

preloaded_audit_agent: Agent[AuditDependencies, AuditReport] = Agent(
    AGENT_MODEL,
    name="audit_preloaded",
    deps_type=AuditDependencies,
    output_type=AuditReport,
    model_settings=config_model_settings(
        temperature=AUDITOR_PERSONA.params.temperature,
        top_p=AUDITOR_PERSONA.params.top_p,
    ),
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)



################
#   PROMPTS
################


@audit_agent.system_prompt
async def build_system_prompt(ctx: RunContext[AuditDependencies]) -> str:
    """
    Build the standalone audit system prompt from deps and the Auditor persona.
    """
    persona_instr = AUDITOR_PERSONA.get_system_instructions()
    rules_block = _format_rules_for_prompt(ctx.deps.rules)
    skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."
    workflow = """1. Call `list_files` to discover what needs auditing.
2. Call `process_batch` iteratively. Pass up to 5 `file_paths` to read, along with `findings_from_previous_batch` (empty on the first call).
3. The tool will return the file contents. Examine them carefully against each rule in the checklist below.
4. Call `process_batch` again with the findings from your current batch, requesting the next batch.
5. After reading all files, call `process_batch` one final time with an empty `file_paths` list to submit the last batch of findings.
6. Call `finalize_report` to produce the final output."""

    return f"""{persona_instr}

## Domain Knowledge
{skills_block}

## Your Task
Analyse every source file in {ctx.deps.package_path}.

{workflow}

## Rules Checklist
{rules_block}

## Analysis Standards
- Report only confirmed issues — do not flag uncertain or speculative problems.
- Every finding MUST have a file_path, line_start, line_end, rule_id, and suggested_fix.
- line numbers are 1-indexed. If you cannot determine exact lines, use the nearest function boundary.
- code_snippet should be the literal offending lines, not paraphrased.
- severity may be escalated from the rule default if context warrants it — explain in description.
- Do NOT report the same issue twice in the same file.
- Missing implementation stubs are findings — do not give benefit of the doubt to empty function bodies.
"""


@preloaded_audit_agent.system_prompt
async def build_preloaded_system_prompt(ctx: RunContext[AuditDependencies]) -> str:
    """
    Build the orchestrated audit prompt for pre-read file batches.

    This agent has no file discovery or batching tools. The Python
    orchestrator owns workflow control and injects the exact file content.
    """
    persona_instr = AUDITOR_PERSONA.get_system_instructions()
    rules_block = _format_rules_for_prompt(ctx.deps.rules)
    skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."

    return f"""{persona_instr}

## Domain Knowledge
{skills_block}

## Pre-loaded Files
{ctx.deps.extra_file_context or 'No files were provided.'}

## Your Task
Analyse only the pre-loaded files above and return an AuditReport directly
as structured output. Do not invent missing file content and do not describe
workflow steps.

## Rules Checklist
{rules_block}

## Analysis Standards
- Report only confirmed issues — do not flag uncertain or speculative problems.
- Every finding MUST have a file_path, line_start, line_end, rule_id, and suggested_fix.
- line numbers are 1-indexed. If you cannot determine exact lines, use the nearest function boundary.
- code_snippet should be the literal offending lines, not paraphrased.
- severity may be escalated from the rule default if context warrants it — explain in description.
- Do NOT report the same issue twice in the same file.
- Missing implementation stubs are findings — do not give benefit of the doubt to empty function bodies.
"""


def _format_rules_for_prompt(rules: list[AuditRule]) -> str:
    """
    Render rules as a numbered checklist for the system prompt.

    Each rule shows its ID, category, default severity, description,
    and any examples to anchor the LLM's pattern recognition.
    """
    lines: list[str] = []

    for i, rule in enumerate(rules, 1):
        lines.append(
            f"{i}. [{rule.rule_id}] ({rule.category.value} / {rule.severity.value})\n"
            f"   {rule.description}"
        )
        for example in rule.examples:
            lines.append(f"   Example: `{example}`")

    return "\n".join(lines)


################
#   TOOLS
################


@audit_agent.tool
async def list_files(ctx: RunContext[AuditDependencies]) -> list[str]:
    """
    List all source files in the package directory.

    Walks the package path recursively and returns paths matching
    the configured file extension. Returns an empty list on error.
    """
    import glob

    pattern = os.path.join(ctx.deps.package_path, f"**/*{ctx.deps.file_extension}")
    return glob.glob(pattern, recursive=True)


@audit_agent.tool
async def process_batch(
    ctx: RunContext[AuditDependencies],
    file_paths: list[str],
    findings_from_previous_batch: list[FileAuditResult],
) -> str:
    """
    Submit findings from the previous batch and receive the next batch of file content.

    Pass an empty list for findings_from_previous_batch on the first call.
    The agent cannot receive new file content without first submitting
    findings for the files it already read. Returns the file contents.
    """
    ctx.deps.file_results.extend(findings_from_previous_batch)

    results = []
    for path in file_paths[:5]:  # hard cap
        content = await _read_file_internal(path)
        results.append(f"### {path}\n{content}")

    if not results:
        return "No files requested. Findings stored."

    return "\n\n".join(results)


async def _read_file_internal(file_path: str) -> str:
    """Internal helper to read file content robustly."""
    if not os.path.exists(file_path):
        return f"ERROR:NOT_FOUND:{file_path}"

    try:
        raw = await anyio.Path(file_path).read_bytes()
    except Exception as exc:
        return f"ERROR:READ_FAILED:{exc}"

    if len(raw) > _MAX_FILE_BYTES:
        truncated = raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
        return truncated + f"\n\n[TRUNCATED — file exceeds {_MAX_FILE_BYTES} bytes]"

    return raw.decode("utf-8", errors="replace")


@audit_agent.tool
async def finalize_report(
    ctx: RunContext[AuditDependencies],
    summary: str,
    partial_failure: bool = False,
) -> AuditReport:
    """
    Aggregate all file results into the final AuditReport.

    Called once after all files have been analysed. Builds stats from
    accumulated FileAuditResult objects and returns the complete report
    as the agent's structured output.
    """
    file_results = ctx.deps.file_results
    stats = _compute_stats(file_results)
    rules_applied = [r.rule_id for r in ctx.deps.rules]

    return AuditReport(
        package_path=ctx.deps.package_path,
        summary=summary,
        file_results=file_results,
        stats=stats,
        rules_applied=rules_applied,
        partial_failure=partial_failure,
    )


################
#   HELPERS
################


def _get_state(ctx: RunContext[AuditDependencies]) -> list[FileAuditResult]:
    """
    Retrieve or initialise the per-run file result accumulator.

    Uses the RunContext's state dict as working memory across tool
    calls within a single agent run.
    """
    return ctx.deps.file_results


def _compute_stats(file_results: list[FileAuditResult]) -> AuditStats:
    """
    Compute aggregated counts from a list of FileAuditResult objects.

    Iterates findings once to produce all summary statistics needed
    by the report writer and downstream consumers.
    """
    by_severity: dict[str, int] = {s.value: 0 for s in Severity}
    by_category: dict[str, int] = {c.value: 0 for c in FindingCategory}
    skipped = sum(1 for fr in file_results if fr.skipped)

    for fr in file_results:
        for finding in fr.findings:
            by_severity[finding.severity.value] += 1
            by_category[finding.category.value] += 1

    total_findings = sum(by_severity.values())

    return AuditStats(
        total_files_analysed=len(file_results) - skipped,
        total_files_skipped=skipped,
        total_findings=total_findings,
        by_severity=by_severity,
        by_category=by_category,
        blocker_count=by_severity.get(Severity.BLOCKER.value, 0),
        critical_count=by_severity.get(Severity.CRITICAL.value, 0),
    )


################
#   RETRY
################


def with_retry(max_attempts: int = _RETRY_MAX) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator that retries an async function with exponential backoff.

    On final failure returns a structured error dict rather than
    raising, so the agent can record a partial_failure rather than
    crashing the entire run.
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    wait = 2 ** (attempt - 1)
                    logger.warning(
                        "Tool '%s' attempt %d/%d failed: %s — retrying in %ds.",
                        fn.__name__, attempt, max_attempts, exc, wait,
                    )
                    if attempt < max_attempts:
                        await asyncio.sleep(wait)

            return {"error": f"Failed after {max_attempts} attempts: {last_exc}"}

        wrapper.__name__ = fn.__name__
        return wrapper

    return decorator
