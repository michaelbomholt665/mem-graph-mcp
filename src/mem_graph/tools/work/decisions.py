"""
tools/work/decisions.py — Architectural decision recording and lineage tools.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Any, cast

import anyio
from fastmcp import FastMCP
from ..markers import tier_2_tool
from pydantic import Field

from ...agents.document.decision_agent import DecisionDependencies, decision_agent
from ...app.registry import AgentEntry, register_agent
from ...db import db_get_connection
from ...embeddings import embeddings_generate
from ...ids import id_generate_v7
from ...services.search import rrf_fuse

logger = logging.getLogger(__name__)

mcp = FastMCP("decisions")

register_agent(
    AgentEntry(
        name="Decision Agent",
        tool_name="decision_review",
        description="Audits architecture for drift against codebase.",
        namespace="audit",
        categories=["architecture", "audit"],
        task_types=["decision_review", "drift_detection"],
    )
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@tier_2_tool
@mcp.tool()
async def decision_record(
    project_id: Annotated[str, Field(description="Owning project ID")],
    title: Annotated[str, Field(description="Short decision title")],
    rationale: Annotated[str, Field(description="Why this decision was made")],
    alternatives: Annotated[
        str | None, Field(description="Rejected alternatives, free text")
    ] = None,
    impact: Annotated[
        str,
        Field(description="Impact level: low | medium | high | critical"),
    ] = "low",
) -> dict:
    """Record a project decision with rationale and impact."""
    conn = db_get_connection()
    decision_id = id_generate_v7()
    text = f"{title}\n{rationale}"
    if alternatives:
        text += f"\nAlternatives: {alternatives}"
    vec = await embeddings_generate(text)

    conn.execute(
        """
        CREATE (d:Decision {
            id: $id,
            title: $title,
            rationale: $rationale,
            alternatives: $alternatives,
            status: 'active',
            impact: $impact,
            embedding: $embedding,
            created_at: $ts
        })
        """,
        {
            "id": decision_id,
            "title": title,
            "rationale": rationale,
            "alternatives": alternatives or "",
            "impact": impact,
            "embedding": vec,
            "ts": _now(),
        },
    )

    conn.execute(
        """
        MATCH (p:Project {id: $project_id}), (d:Decision {id: $decision_id})
        CREATE (p)-[:HAS_DECISION]->(d)
        """,
        {"project_id": project_id, "decision_id": decision_id},
    )

    return {"decision_id": decision_id}


@tier_2_tool
@mcp.tool(tags={"namespace:work"})
async def decision_supersede(
    old_id: Annotated[str, Field(description="ID of the decision being superseded")],
    new_id: Annotated[
        str, Field(description="ID of the new decision that supersedes it")
    ],
    reason: Annotated[
        str, Field(description="Why the old decision is being superseded")
    ],
) -> dict:
    """Mark one decision as superseded by another."""
    conn = db_get_connection()
    ts = _now()

    conn.execute(
        """
        MATCH (d:Decision {id: $old_id})
        SET d.status = 'superseded'
        """,
        {"old_id": old_id},
    )

    conn.execute(
        """
        MATCH (new_d:Decision {id: $new_id}), (old_d:Decision {id: $old_id})
        CREATE (new_d)-[:SUPERSEDES {reason: $reason, superseded_at: $ts}]->(old_d)
        """,
        {"new_id": new_id, "old_id": old_id, "reason": reason, "ts": ts},
    )

    return {"ok": True}


@tier_2_tool
@mcp.tool(tags={"namespace:work"})
async def decision_get(
    decision_id: Annotated[str, Field(description="Decision ID to retrieve")],
) -> dict:
    """Retrieve a decision and its supersession lineage."""
    conn = db_get_connection()

    result = conn.execute(
        """
        MATCH (d:Decision {id: $id})
        RETURN d.id, d.title, d.rationale, d.alternatives, d.status, d.impact, d.created_at
        """,
        {"id": decision_id},
    )
    if isinstance(result, list):
        result = result[0]
    rows = cast(list[list[Any]], result.get_all())
    if not rows:
        return {"error": f"Decision {decision_id!r} not found"}

    r = rows[0]
    decision: dict[str, Any] = {
        "id": r[0],
        "title": r[1],
        "rationale": r[2],
        "alternatives": r[3],
        "status": r[4],
        "impact": r[5],
        "created_at": str(r[6]),
    }

    lineage_result = conn.execute(
        """
        MATCH (d:Decision {id: $id})-[s:SUPERSEDES*]->(old:Decision)
        RETURN old.id, old.title, old.status
        """,
        {"id": decision_id},
    )
    if isinstance(lineage_result, list):
        lineage_result = lineage_result[0]
    decision["supersedes"] = [
        {"id": row[0], "title": row[1], "status": row[2]}
        for row in cast(list[list[Any]], lineage_result.get_all())
    ]

    supd_result = conn.execute(
        """
        MATCH (newer:Decision)-[:SUPERSEDES]->(d:Decision {id: $id})
        RETURN newer.id, newer.title
        """,
        {"id": decision_id},
    )
    if isinstance(supd_result, list):
        supd_result = supd_result[0]
    decision["superseded_by"] = [
        {"id": row[0], "title": row[1]}
        for row in cast(list[list[Any]], supd_result.get_all())
    ]

    return {"decision": decision}


@tier_2_tool
@mcp.tool()
async def decision_search(
    query: Annotated[str, Field(description="Natural language search query")],
    project_id: Annotated[
        str | None, Field(description="Scope to a specific project")
    ] = None,
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=20)] = 10,
) -> dict:
    """Search decisions by semantic similarity."""
    conn = db_get_connection()
    vec = await embeddings_generate(query)
    candidate_size = limit * 3

    vector_raw = conn.execute(
        """
        CALL QUERY_VECTOR_INDEX('Decision', 'idx_decision_emb', $qvec, $candidate_size)
        WITH node AS d, distance
        OPTIONAL MATCH (p:Project)-[:HAS_DECISION]->(d)
        RETURN d.id, d.title, d.rationale, d.status, d.impact, p.id AS project_id, distance
        ORDER BY distance
        LIMIT $candidate_size
        """,
        {"qvec": vec, "candidate_size": candidate_size},
    )
    if isinstance(vector_raw, list):
        vector_raw = vector_raw[0]
    vector_rows = cast(list[list[Any]], vector_raw.get_all())

    fts_raw = conn.execute(
        """
        CALL QUERY_FTS_INDEX('Decision', 'fts_decision_rat', $q)
        WITH node AS d, score
        OPTIONAL MATCH (p:Project)-[:HAS_DECISION]->(d)
        RETURN d.id, d.title, d.rationale, d.status, d.impact, p.id AS project_id, score
        ORDER BY score DESC
        LIMIT $candidate_size
        """,
        {"q": query, "candidate_size": candidate_size},
    )
    if isinstance(fts_raw, list):
        fts_raw = fts_raw[0]
    fts_rows = cast(list[list[Any]], fts_raw.get_all())

    vector_hits = [(row[0], float(row[6])) for row in vector_rows]
    fts_hits = [(row[0], float(rank)) for rank, row in enumerate(fts_rows, start=1)]
    ranks = dict(rrf_fuse(vector_hits, fts_hits))

    data_map: dict[str, list[Any]] = {row[0]: row for row in vector_rows}
    for row in fts_rows:
        data_map[row[0]] = row

    decisions = []
    for node_id, _ in sorted(ranks.items(), key=lambda item: item[1], reverse=True):
        if node_id not in data_map:
            continue
        r = data_map[node_id]
        if project_id and r[5] != project_id:
            continue
        decisions.append(
            {
                "id": r[0],
                "title": r[1],
                "rationale": r[2],
                "status": r[3],
                "impact": r[4],
                "project_id": r[5],
                "distance": 1.0 - ranks[node_id],
            }
        )
        if len(decisions) >= limit:
            break

    return {"decisions": decisions, "query": query}


async def _load_decision_skills() -> str:
    path = os.path.join(os.getcwd(), "skills", "decision_agent", "SKILL.md")
    if not os.path.exists(path):
        return ""
    try:
        async with await anyio.open_file(path, "r", encoding="utf-8") as f:
            return await f.read()
    except Exception as exc:
        logger.warning("Failed to load skills: %s", exc)
        return ""


@tier_2_tool
@mcp.tool(tags={"namespace:audit"})
async def decision_review(
    project_id: Annotated[str, Field(description="Project ID")],
    package_path: Annotated[str, Field(description="Package path to review against")],
) -> dict:
    """Audit active project decisions for code drift."""
    conn = db_get_connection()
    result = conn.execute(
        """
        MATCH (p:Project {id: $project_id})-[:HAS_DECISION]->(d:Decision)
        WHERE d.status = 'active'
        RETURN d.id, d.title, d.rationale, d.alternatives, d.status, d.impact
        """,
        {"project_id": project_id},
    )
    if isinstance(result, list):
        result = result[0]

    decisions = [
        {
            "id": row[0],
            "title": row[1],
            "rationale": row[2],
            "alternatives": row[3],
            "status": row[4],
            "impact": row[5],
        }
        for row in cast(list[list[Any]], result.get_all())
    ]

    if not decisions:
        return {
            "summary": "No active decisions to review.",
            "honoured": 0,
            "drifted": 0,
        }

    skills_content = await _load_decision_skills()
    deps = DecisionDependencies(
        project_id=project_id,
        package_path=package_path,
        decisions=decisions,
        skills_content=skills_content,
    )

    try:
        async with decision_agent.run_stream(
            "Review decisions against codebase by calling process_batch.",
            deps=deps,
        ) as run_result:
            report = await run_result.get_output()
    except Exception as exc:
        logger.error("Decision agent execution failed: %s", exc)
        return {"error": f"Agent failed: {exc}"}

    return {
        "status": "completed" if not report.partial_failure else "partial",
        "summary": report.summary,
        "honoured": report.honoured_count,
        "drifted": report.drifted_count,
        "unverifiable": report.unverifiable_count,
    }
