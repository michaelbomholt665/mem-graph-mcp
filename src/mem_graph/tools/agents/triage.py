#!/usr/bin/env python3
# src/mem_graph/tools/agents/triage.py
"""
MCP tool surface for the triage agent.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, cast

import anyio
from fastmcp import FastMCP
from pydantic import Field

from ...agents.triage_agent import TriageDependencies, RawFinding, triage_agent
from ...db import get_conn

mcp = FastMCP("triage", instructions="Code violation triage tools.")
logger = logging.getLogger(__name__)

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


@mcp.tool(tags={"namespace:audit"})
async def triage_violations(
    project_id: Annotated[str, Field(description="Project ID.")],
    raw_findings: Annotated[
        list[dict],
        Field(description="List of raw findings dicts (rule_id, file_path, description, severity, source, line_start, line_end)."),
    ] = [],
) -> dict:
    """
    Triage and classify raw code findings against existing open violations in the graph.

    Deduplicates recurrences, assesses severity, and categorizes findings as
    NEW, RECURRENCE, DUPLICATE, WONTFIX, or ESCALATE. Returns a structured
    triage report with counts per category.
    """
    conn = get_conn()
    existing = _fetch_existing_violations(conn, project_id)
    findings = [_build_finding(f) for f in raw_findings]

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
