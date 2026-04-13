#!/usr/bin/env python3
# src/mem_graph/tools/agents/audit.py
"""
MCP tool surface for the audit agent.

Exposes audit_package as the single entry point for codebase audits.
Loads skills from disk, runs the audit agent, optionally writes findings
to the graph, and returns a structured summary to the MCP caller.

FastMCP 3.0 upgrades:
- ``ctx: Context`` injected for progress reporting, client logging, and sampling.
- ``ctx.report_progress()`` called at each audit phase.
- ``ctx.sample()`` used to request a peer review of findings from the client LLM.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

import anyio
from fastmcp import FastMCP
from fastmcp.server.context import Context
from mcp.types import Icon
from pydantic import Field

from ...agents.audit.audit_agent import DEFAULT_RULES, AuditDependencies, audit_agent
from ...models.audit import AuditReport
from ...services.report_writer import write_report
from ...services.violation_writer import write_violations

mcp = FastMCP("audit", instructions="Perform package codebase audits.")
logger = logging.getLogger(__name__)

_SKILLS_PATH = os.path.join(os.getcwd(), "skills", "audit_agent", "SKILL.md")


@mcp.tool(
    tags={"namespace:audit"},
    icons=[Icon(src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0Ij48cGF0aCBkPSJNMTIgMkM2LjQ4IDIgMiA2LjQ4IDIgMTJzNC40OCAxMCAxMCAxMCAxMC00LjQ4IDEwLTEwUzE3LjUyIDIgMTIgMnptMCA4Yy0xLjEgMC0yLS45LTIgLTJzMi45IDIgMi4yLjktMl6CTEwIEgzMDU2UzAgMjcgNzZ6bS00LTJoMnYyaC0yeiIvPjwvc3ZnPg==", mimeType="image/svg+xml")],
    task=True
)
async def audit_package(
    package_path: Annotated[
        str,
        Field(
            description=(
                "Absolute path to the package directory to audit, e.g. "
                "/home/michael/projects/go/lakehouse/internal/managers/database"
            )
        ),
    ],
    project_id: Annotated[
        str,
        Field(description="mem-graph project ID to link findings against as Violation nodes."),
    ],
    report_output_path: Annotated[
        str | None,
        Field(description="Optional absolute path to write the markdown report. Omit to skip."),
    ] = None,
    persist_violations: Annotated[
        bool,
        Field(description="Write findings to the graph as Violation nodes. Defaults to True."),
    ] = True,
    file_extension: Annotated[
        str,
        Field(description="Source file extension to analyse. Defaults to '.py'."),
    ] = ".py",
    peer_review: Annotated[
        bool,
        Field(description="Request an LLM peer review of the findings summary before returning. Defaults to False."),
    ] = False,
    ctx: Context = None,  # type: ignore[assignment]
) -> dict:
    """
    Audit and analyse a source code package directory for bugs, violations, security issues, and missing implementations.

    Analyses all source files for bugs, goroutine leaks, silent errors, security
    vulnerabilities, and missing implementations. Deduplicates findings against
    existing open violations and marks recurrences. Returns a structured summary
    with finding counts and severity breakdown.

    Pass ``peer_review=True`` to have the findings reviewed by the client LLM
    before they are returned.
    """
    if not os.path.exists(package_path):
        return {"error": f"Package path not found: {package_path}"}

    await _report_progress_init(ctx, package_path)

    skills_content = await _load_skills()
    deps = _build_deps(package_path, file_extension, skills_content)

    await _report_progress_running(ctx)

    report = await _run_agent(deps)

    if report is None:
        return {"error": "Audit agent failed to produce a report."}

    await _report_progress_complete(ctx, report)
    output_path = _maybe_write_report(report, report_output_path)
    
    violation_summary = await _handle_violation_persistence(
        ctx, report, project_id, persist_violations
    )

    await _report_progress_persistence(ctx)

    peer_review_result = await _handle_peer_review(ctx, report, peer_review)

    await _report_progress_final(ctx)

    response = _build_response(report, output_path, violation_summary)
    if peer_review_result is not None:
        response["peer_review"] = peer_review_result
    return response


async def _report_progress_init(ctx: Context | None, package_path: str) -> None:
    """Report initial progress."""
    if ctx is not None:
        await ctx.info(f"Starting audit of {package_path}")
        await ctx.report_progress(progress=0, total=4)


async def _report_progress_running(ctx: Context | None) -> None:
    """Report agent running progress."""
    if ctx is not None:
        await ctx.info("Running audit agent…")
        await ctx.report_progress(progress=1, total=4)


async def _report_progress_complete(ctx: Context | None, report: AuditReport) -> None:
    """Report audit complete progress."""
    if ctx is not None:
        await ctx.info(
            f"Audit complete: {report.stats.total_findings} findings "
            f"({report.stats.blocker_count} blockers)."
        )
        await ctx.report_progress(progress=2, total=4)


async def _report_progress_persistence(ctx: Context | None) -> None:
    """Report persistence progress."""
    if ctx is not None:
        await ctx.report_progress(progress=3, total=4)


async def _report_progress_final(ctx: Context | None) -> None:
    """Report final progress."""
    if ctx is not None:
        await ctx.report_progress(progress=4, total=4)


async def _handle_violation_persistence(
    ctx: Context | None,
    report: AuditReport,
    project_id: str,
    persist_violations: bool,
) -> str:
    """Handle violation persistence logic with optional user confirmation."""
    if not persist_violations:
        return "Violation persistence skipped."

    has_critical_findings = (
        report.stats.blocker_count > 0 or report.stats.critical_count > 0
    )

    if not has_critical_findings:
        return _maybe_persist(report, project_id, persist_violations)

    # Request user confirmation for critical findings
    if ctx is None:
        return _maybe_persist(report, project_id, persist_violations)

    try:
        from fastmcp.server.context import AcceptedElicitation

        critical_desc = (
            f"Found {report.stats.blocker_count} blocker(s) and "
            f"{report.stats.critical_count} critical issue(s). "
            "Proceed with persisting these violations to the graph?"
        )
        confirmation = await ctx.elicit(
            message=critical_desc,
            response_type=["yes", "no"],  # type: ignore[arg-type]
        )

        if isinstance(confirmation, AcceptedElicitation) and confirmation.data == "yes":
            return _maybe_persist(report, project_id, persist_violations)
        return "User declined to persist critical violations."

    except Exception as exc:
        logger.debug("Confirmation unavailable, persisting violations anyway: %s", exc)
        return _maybe_persist(report, project_id, persist_violations)


async def _handle_peer_review(
    ctx: Context | None,
    report: AuditReport,
    peer_review: bool,
) -> str | None:
    """Handle optional LLM peer review via FastMCP 3.0 sampling."""
    if not peer_review or ctx is None or not report.summary:
        return None

    try:
        peer_prompt = (
            "Please review the following audit findings summary and highlight "
            "anything that seems incorrect, underweighted, or missing:\n\n"
            f"{report.summary}"
        )
        sample_result = await ctx.sample(peer_prompt, max_tokens=512)
        peer_review_result = getattr(sample_result, "text", str(sample_result))
        await ctx.info("Peer review complete.")
        return peer_review_result
    except Exception as exc:
        logger.warning("Peer review sampling failed: %s", exc)
        return None


async def _load_skills() -> str:
    if not os.path.exists(_SKILLS_PATH):
        return ""

    try:
        async with await anyio.open_file(_SKILLS_PATH, "r", encoding="utf-8") as f:
            return await f.read()
    except Exception as exc:
        logger.warning("Failed to load skills from %s: %s", _SKILLS_PATH, exc)
        return ""


def _build_deps(package_path: str, file_extension: str, skills_content: str) -> AuditDependencies:
    return AuditDependencies(
        package_path=package_path,
        file_extension=file_extension,
        skills_content=skills_content,
        rules=DEFAULT_RULES,
    )


async def _run_agent(deps: AuditDependencies) -> AuditReport | None:
    prompt = (
        "Begin the audit. List all source files, read and analyse each one "
        "against the rules checklist, record findings per file, then finalize the report."
    )

    try:
        async with audit_agent.run_stream(prompt, deps=deps) as result:
            return await result.get_output()
    except Exception as exc:
        logger.error("Audit agent execution failed: %s", exc)
        return None


def _maybe_write_report(report: AuditReport, output_path: str | None) -> str | None:
    if not output_path:
        return None

    try:
        return write_report(report, output_path)
    except Exception as exc:
        logger.error("Failed to write report to %s: %s", output_path, exc)
        return None


def _maybe_persist(report: AuditReport, project_id: str, persist: bool) -> str:
    if not persist:
        return "Violation persistence skipped."

    try:
        result = write_violations(report, project_id)
        return f"{result.created} new violation(s), {result.recurrences} recurrence(s)."
    except Exception as exc:
        logger.error("Violation write failed: %s", exc)
        return f"Violation write failed: {exc}"


def _build_response(report: AuditReport, output_path: str | None, violation_summary: str) -> dict:
    return {
        "status": "completed" if not report.partial_failure else "partial",
        "summary": report.summary,
        "total_findings": report.stats.total_findings,
        "blockers": report.stats.blocker_count,
        "criticals": report.stats.critical_count,
        "by_severity": report.stats.by_severity,
        "by_category": report.stats.by_category,
        "files_analysed": report.stats.total_files_analysed,
        "files_skipped": report.stats.total_files_skipped,
        "violations_written": violation_summary,
        "report_path": output_path,
        "has_blockers": report.has_blockers,
    }
