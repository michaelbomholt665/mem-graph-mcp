#!/usr/bin/env python3
# src/mem_graph/tools/agents/audit.py
"""
MCP tool surface for the audit agent.

Exposes audit_package as the single entry point for codebase audits.
Loads skills from disk, runs the audit agent, optionally writes findings
to the graph, and returns a structured summary to the MCP caller.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

import anyio
from fastmcp import FastMCP
from pydantic import Field

from ...agents.audit_agent import DEFAULT_RULES, AuditDependencies, audit_agent
from ...models.audit import AuditReport
from ...services.report_writer import write_report
from ...services.violation_writer import write_violations

mcp = FastMCP("audit", instructions="Perform package codebase audits.")
logger = logging.getLogger(__name__)

_SKILLS_PATH = os.path.join(os.getcwd(), "skills", "audit_agent", "SKILL.md")


@mcp.tool(tags={"namespace:audit"})
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
) -> dict:
    """
    Audit and analyse a source code package directory for bugs, violations, security issues, and missing implementations.

    Analyses all source files for bugs, goroutine leaks, silent errors, security
    vulnerabilities, and missing implementations. Deduplicates findings against
    existing open violations and marks recurrences. Returns a structured summary
    with finding counts and severity breakdown.
    """
    if not os.path.exists(package_path):
        return {"error": f"Package path not found: {package_path}"}

    skills_content = await _load_skills()
    deps = _build_deps(package_path, file_extension, skills_content)
    report = await _run_agent(deps)

    if report is None:
        return {"error": "Audit agent failed to produce a report."}

    output_path = _maybe_write_report(report, report_output_path)
    violation_summary = _maybe_persist(report, project_id, persist_violations)

    return _build_response(report, output_path, violation_summary)


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
