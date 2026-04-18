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

################
#   CONSTANTS
################

_MAX_FILE_BYTES = 64_000
_RETRY_MAX = 3

logger = logging.getLogger(__name__)

################
#   DEFAULT RULES
################

DEFAULT_RULES: list[AuditRule] = [
    AuditRule(
        rule_id="go:ignored-error",
        category=FindingCategory.SILENT_ERROR,
        severity=Severity.MAJOR,
        description=(
            "Error return values assigned to blank identifier `_` or not checked at all. "
            "Includes ignored os.File.Close(), sql.Rows.Close(), io.Writer.Write(), "
            "and any function returning (T, error) where the error is discarded."
        ),
        examples=["f, _ := os.Open(path)", "rows.Close()  // return value dropped"],
    ),
    AuditRule(
        rule_id="go:context-not-propagated",
        category=FindingCategory.LEAK,
        severity=Severity.MAJOR,
        description=(
            "Functions accepting context.Context that do not pass it to downstream "
            "calls (DB queries, HTTP requests, goroutines). Results in ungraceful "
            "shutdown and leaked goroutines on cancellation."
        ),
        examples=["db.Query(sql) instead of db.QueryContext(ctx, sql)"],
    ),
    AuditRule(
        rule_id="go:goroutine-leak",
        category=FindingCategory.LEAK,
        severity=Severity.CRITICAL,
        description=(
            "Goroutines launched with `go func()` that have no guaranteed termination "
            "path — missing done channel, WaitGroup, or context cancellation handling. "
            "Also covers goroutines blocked on unbuffered channels with no sender."
        ),
        examples=["go func() { for { work() } }()  // no exit condition"],
    ),
    AuditRule(
        rule_id="go:deferred-in-loop",
        category=FindingCategory.LEAK,
        severity=Severity.MAJOR,
        description=(
            "defer statements inside for loops. Deferred calls execute at function "
            "return, not loop iteration end — file handles and locks accumulate until "
            "the enclosing function exits."
        ),
        examples=["for _, f := range files { defer f.Close() }"],
    ),
    AuditRule(
        rule_id="CWE-252",
        category=FindingCategory.BUG,
        severity=Severity.MAJOR,
        description=(
            "Unchecked return values from functions that signal failure via return "
            "value rather than panic. Includes fmt.Fprintf, json.Marshal, "
            "strconv.Atoi used without error check."
        ),
        examples=["json.Marshal(v)  // return value and error both discarded"],
    ),
    AuditRule(
        rule_id="CWE-400",
        category=FindingCategory.BUG,
        severity=Severity.MAJOR,
        description=(
            "Uncontrolled resource consumption — unbounded loops reading from "
            "external input, slices grown without capacity hints in hot paths, "
            "recursive functions without depth limits."
        ),
        examples=["for { data = append(data, readChunk()) }  // no size cap"],
    ),
    AuditRule(
        rule_id="security:hardcoded-secret",
        category=FindingCategory.SECURITY,
        severity=Severity.BLOCKER,
        description=(
            "Hardcoded credentials, API keys, tokens, passwords, or private keys "
            "in source code. Includes string literals assigned to variables named "
            "password, secret, key, token, apikey, or matching common secret patterns."
        ),
        examples=['password := "hunter2"', 'const APIKey = "sk-..."'],
    ),
    AuditRule(
        rule_id="security:sql-injection",
        category=FindingCategory.SECURITY,
        severity=Severity.BLOCKER,
        description=(
            "String concatenation or fmt.Sprintf used to build SQL query strings "
            "with user-controlled input. Parameterised queries must be used instead."
        ),
        examples=['query := "SELECT * FROM users WHERE id = " + userID'],
    ),
    AuditRule(
        rule_id="security:unsafe-deserialization",
        category=FindingCategory.SECURITY,
        severity=Severity.CRITICAL,
        description=(
            "Deserialisation of untrusted input into interface{} or any without "
            "schema validation. Includes gob.Decode, json.Unmarshal into interface{}, "
            "yaml.Unmarshal without struct target."
        ),
        examples=["json.Unmarshal(userInput, &interface{}{})"],
    ),
    AuditRule(
        rule_id="impl:stub-in-production",
        category=FindingCategory.MISSING_IMPLEMENTATION,
        severity=Severity.MAJOR,
        description=(
            "Functions or methods that return zero values, empty structs, or nil "
            "without performing real work — stub implementations that were never "
            "completed. Includes panic('not implemented'), empty interface implementations."
        ),
        examples=["func (r *Repo) Save(x X) error { return nil }  // no actual write"],
    ),
    AuditRule(
        rule_id="impl:missing-error-context",
        category=FindingCategory.BUG,
        severity=Severity.MINOR,
        description=(
            "Errors returned without wrapping or context. Raw sentinel errors or "
            "bare `return err` that lose the call site context needed for debugging. "
            "Should use fmt.Errorf with %w or a structured error type."
        ),
        examples=["if err != nil { return err }  // no context added"],
    ),
    AuditRule(
        rule_id="impl:panic-in-library",
        category=FindingCategory.BUG,
        severity=Severity.CRITICAL,
        description=(
            "panic() calls in library or service code outside of main() and init(). "
            "Panics in non-main packages crash the entire process and cannot be "
            "handled by callers. Return errors instead."
        ),
        examples=["panic(fmt.Sprintf('unexpected state: %v', s))"],
    ),
]

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



################
#   PROMPTS
################


@audit_agent.system_prompt
async def build_system_prompt(ctx: RunContext[AuditDependencies]) -> str:
    """
    Build the system prompt from deps and the Auditor persona at runtime.
    """
    persona_instr = AUDITOR_PERSONA.get_system_instructions()
    rules_block = _format_rules_for_prompt(ctx.deps.rules)
    skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."
    if ctx.deps.extra_file_context:
        file_section = (
            "## Pre-loaded Files\n"
            f"{ctx.deps.extra_file_context}\n\n"
            "The files above were pre-loaded by the orchestrator."
        )
        workflow = """1. Analyse only the pre-loaded files shown above.
2. Return the final AuditReport directly as structured output.
3. Do not call list_files, process_batch, or finalize_report."""
        analysis_scope = "the pre-loaded files"
    else:
        file_section = ""
        workflow = """1. Call `list_files` to discover what needs auditing.
2. Call `process_batch` iteratively. Pass up to 5 `file_paths` to read, along with `findings_from_previous_batch` (empty on the first call).
3. The tool will return the file contents. Examine them carefully against each rule in the checklist below.
4. Call `process_batch` again with the findings from your current batch, requesting the next batch.
5. After reading all files, call `process_batch` one final time with an empty `file_paths` list to submit the last batch of findings.
6. Call `finalize_report` to produce the final output."""
        analysis_scope = f"every source file in {ctx.deps.package_path}"

    return f"""{persona_instr}

## Domain Knowledge
{skills_block}

{file_section}

## Your Task
Analyse {analysis_scope}.

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
    _get_state(ctx).extend(findings_from_previous_batch)

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
    file_results = _get_state(ctx)
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
    if not hasattr(ctx, "_audit_state"):
        ctx._audit_state = []  # type: ignore[attr-defined]
    return ctx._audit_state  # type: ignore[attr-defined]


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