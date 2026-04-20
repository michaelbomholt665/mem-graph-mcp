#!/usr/bin/env python3
# src/mem_graph/tools/agents/triage.py
"""
MCP tool surface for the triage agent.

FastMCP 3.0 upgrades:
- ``ctx: Context`` injected for progress reporting and client logging.
- ``Depends(db_get_connection)`` injects the DB connection via FastMCP DI.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, cast

import anyio
from fastmcp import FastMCP
from ..markers import tier_2_tool
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from mcp.types import Icon
from pydantic import Field

from ...app.registry import AgentEntry, register_agent
from ...agents.document.triage_agent import TriageDependencies, RawFinding, triage_agent
from ...db import db_get_connection
from ...observability import traced_tool
from ...services.task_queue import task_queue
from ..background.progress import ContextProgressReporter, ProgressReporter, report_step
from ..background.task_status import build_task_submission

mcp = FastMCP("triage", instructions="Code violation triage tools.")
logger = logging.getLogger(__name__)

register_agent(
    AgentEntry(
        name="Triage Agent",
        tool_name="triage_violations",
        description="Classifies and deduplicates raw code findings.",
        namespace="audit",
        categories=["audit", "quality"],
        task_types=["violation_triage", "deduplication", "severity_review"],
    )
)

_SKILLS_PATH = os.path.join(os.getcwd(), "skills", "triage_agent", "SKILL.md")


async def _load_skills() -> str:
    if not os.path.exists(_SKILLS_PATH):
        return ""
    try:
        async with await anyio.open_file(_SKILLS_PATH, "r", encoding="utf-8") as f:
            return await f.read()
    except Exception as exc:
        logger.warning("Failed to load skills from %s: %s", _SKILLS_PATH, exc)
        return ""


def _build_finding(f: dict) -> RawFinding:
    return RawFinding(
        rule_id=f.get("rule_id", "unknown"),
        file_path=f.get("file_path", "unknown"),
        description=f.get("description", ""),
        severity=f.get("severity", "minor"),
        source=f.get("source", "unknown"),
        line_start=f.get("line_start", 0),
        line_end=f.get("line_end", 0),
    )


def _fetch_existing_violations(conn: Any, project_id: str) -> list[dict]:
    result = conn.execute(
        """
        MATCH (p:Project {id: $project_id})-[:HAS_VIOLATION]->(v:Violation)
        WHERE v.status = 'open'
        RETURN v.id, v.rule, v.file_path, v.line_start, v.status
        """,
        {"project_id": project_id},
    )
    if isinstance(result, list):
        result = result[0]
    return [
        {
            "id": row[0],
            "rule": row[1],
            "file_path": row[2],
            "line_start": row[3],
            "status": row[4],
        }
        for row in cast(list[list[Any]], result.get_all())
    ]


@tier_2_tool
@mcp.tool(
    tags={"namespace:audit"},
    icons=[Icon(src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0Ij48cGF0aCBkPSJNMTkgMkgtNWMtMS4xIDAtMiAuOS0yIDJ2MTRjMCAxLjEuOSAyIDIgMmgxNGMxLjEgMCAyLS45IDItMlY0YzAtMS4xLS45LTItMi0yem0wIDE2aC01di00aDV2NHptMC02aC01YzAgMi4yMS0xLjc5IDQtNCA0cy00LTEuNzktNC00aDAuNzF2LTJIMTZ2Mnd6bTAgOHYtNGgydjR6Ii8+PC9zdmc+", mimeType="image/svg+xml")],
    task=True
)
async def triage_violations(
    project_id: Annotated[str, Field(description="Project ID.")],
    raw_findings: Annotated[
        list[dict],
        Field(description="List of raw findings dicts (rule_id, file_path, description, severity, source, line_start, line_end)."),
    ] = [],
    ctx: Context = None,  # type: ignore[assignment]
    conn: Any = Depends(db_get_connection),
) -> dict:
    """Triage raw findings against existing violations."""
    if ctx is not None and ctx.is_background_task:
        reporter = ContextProgressReporter(ctx)
        return await _triage_violations_worker(
            project_id=project_id,
            raw_findings=raw_findings,
            reporter=reporter,
            ctx=ctx,
            conn=conn,
        )

    task = await task_queue.enqueue(
        tool_name="triage_violations",
        arguments={"project_id": project_id, "raw_findings": raw_findings},
        session_id=ctx.session_id if ctx is not None else None,
        runner=lambda reporter: _triage_violations_worker(
            project_id=project_id,
            raw_findings=raw_findings,
            reporter=reporter,
            ctx=ctx,
            conn=conn,
        ),
    )
    return build_task_submission(task)
@traced_tool("triage_violations", component="tool.worker")
async def _triage_violations_worker(
    *,
    project_id: str,
    raw_findings: list[dict],
    reporter: ProgressReporter,
    ctx: Context | None,
    conn: Any,
) -> dict:
    await report_step(
        reporter,
        10,
        100,
        "prepare",
        f"Preparing triage for {len(raw_findings)} findings in project {project_id}.",
    )

    existing = _fetch_existing_violations(conn, project_id)
    findings = [_build_finding(f) for f in raw_findings]

    await report_step(
        reporter,
        25,
        100,
        "triage",
        f"Running the triage agent against {len(existing)} existing violations.",
    )

    skills_content = await _load_skills()
    deps = TriageDependencies(
        project_id=project_id,
        raw_findings=findings,
        existing_violations=existing,
        skills_content=skills_content,
    )

    try:
        async with triage_agent.run_stream(
            "Begin triage. Read batches using process_batch, triage against existing, and finalize.",
            deps=deps,
        ) as run_result:
            report = await run_result.get_output()
    except Exception as exc:
        logger.error("Triage agent execution failed: %s", exc)
        return {"error": f"Agent failed: {exc}"}

    await report_step(
        reporter,
        82,
        100,
        "review",
        (
            f"Triage complete: {report.new_count} new, {report.recurrence_count} recurrences, "
            f"{report.escalated_count} escalated."
        ),
    )

    if ctx is not None and report.escalated_count > 0:
        try:
            from fastmcp.server.elicitation import AcceptedElicitation

            escalation_desc = (
                f"Found {report.escalated_count} violation(s) to escalate. "
                "Proceed with escalation?"
            )
            confirmation = await ctx.elicit(
                message=escalation_desc,
                response_type=["yes", "no"],  # type: ignore[arg-type]
            )
            if not isinstance(confirmation, AcceptedElicitation) or confirmation.data != "yes":
                logger.info("User declined escalation.")
        except Exception as exc:
            logger.debug("Confirmation unavailable for escalation: %s", exc)

    await report_step(
        reporter,
        100,
        100,
        "complete",
        "Violation triage finished and results are ready.",
    )

    return {
        "status": "completed" if not report.partial_failure else "partial",
        "summary": report.summary,
        "total_input": report.total_input,
        "new": report.new_count,
        "recurrence": report.recurrence_count,
        "duplicate": report.duplicate_count,
        "escalated": report.escalated_count,
        "wontfix": report.wontfix_count,
    }
