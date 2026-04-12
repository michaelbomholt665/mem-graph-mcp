"""
tools/decisions.py — Architectural decision recording and lineage tools.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from pydantic import Field

from ..db import get_conn
from ..embeddings import embed

mcp = FastMCP("decisions")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


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
    """
    Record an architectural or implementation decision.

    Embeds title + rationale for semantic search.
    Links to the project via HAS_DECISION.
    Returns the new decision_id.
    """
    conn = get_conn()
    decision_id = _new_id()
    text = f"{title}\n{rationale}"
    if alternatives:
        text += f"\nAlternatives: {alternatives}"
    vec = await embed(text)

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


@mcp.tool(tags={"namespace:decision"})
async def decision_supersede(
    old_id: Annotated[str, Field(description="ID of the decision being superseded")],
    new_id: Annotated[
        str, Field(description="ID of the new decision that supersedes it")
    ],
    reason: Annotated[
        str, Field(description="Why the old decision is being superseded")
    ],
) -> dict:
    """
    Mark a decision as superseded and link it to its replacement.

    Creates a SUPERSEDES relationship from new → old and sets the old
    decision's status to 'superseded'.
    """
    conn = get_conn()
    ts = _now()

    # Update old decision status
    conn.execute(
        """
        MATCH (d:Decision {id: $old_id})
        SET d.status = 'superseded'
        """,
        {"old_id": old_id},
    )

    # Create supersession edge (new → old, like a forward pointer in lineage)
    conn.execute(
        """
        MATCH (new_d:Decision {id: $new_id}), (old_d:Decision {id: $old_id})
        CREATE (new_d)-[:SUPERSEDES {reason: $reason, superseded_at: $ts}]->(old_d)
        """,
        {"new_id": new_id, "old_id": old_id, "reason": reason, "ts": ts},
    )

    return {"ok": True}


@mcp.tool(tags={"namespace:decision"})
async def decision_get(
    decision_id: Annotated[str, Field(description="Decision ID to retrieve")],
) -> dict:
    """
    Return a decision node with its full supersession lineage.
    """
    conn = get_conn()

    result = conn.execute(
        """
        MATCH (d:Decision {id: $id})
        RETURN d.id, d.title, d.rationale, d.alternatives, d.status, d.impact, d.created_at
        """,
        {"id": decision_id},
    )
    rows = cast(list[list[Any]], result)
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

    # Supersession lineage (decisions this one supersedes)
    lineage_result = conn.execute(
        """
        MATCH (d:Decision {id: $id})-[s:SUPERSEDES*]->(old:Decision)
        RETURN old.id, old.title, old.status
        """,
        {"id": decision_id},
    )
    decision["supersedes"] = [
        {"id": r[0], "title": r[1], "status": r[2]} for r in cast(list[list[Any]], lineage_result)
    ]

    # Decisions that supersede this one
    supd_result = conn.execute(
        """
        MATCH (newer:Decision)-[:SUPERSEDES]->(d:Decision {id: $id})
        RETURN newer.id, newer.title
        """,
        {"id": decision_id},
    )
    decision["superseded_by"] = [
        {"id": r[0], "title": r[1]} for r in cast(list[list[Any]], supd_result)
    ]

    return {"decision": decision}


@mcp.tool()
async def decision_search(
    query: Annotated[str, Field(description="Natural language search query")],
    project_id: Annotated[
        str | None, Field(description="Scope to a specific project")
    ] = None,
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=20)] = 10,
) -> dict:
    """Semantic search over decisions by title+rationale similarity."""
    conn = get_conn()
    vec = await embed(query)

    result = conn.execute(
        f"""
        CALL QUERY_VECTOR_INDEX('Decision', 'idx_decision_emb', $qvec, {limit * 3})
        WITH node AS d, distance
        OPTIONAL MATCH (p:Project)-[:HAS_DECISION]->(d)
        RETURN d.id, d.title, d.status, d.impact, p.id AS project_id, distance
        ORDER BY distance
        LIMIT {limit * 3}
        """,
        {"qvec": vec},
    )

    decisions = []
    for r in cast(list[list[Any]], result):
        if project_id and r[4] != project_id:
            continue
        decisions.append(
            {
                "id": r[0],
                "title": r[1],
                "status": r[2],
                "impact": r[3],
                "project_id": r[4],
                "distance": r[5],
            }
        )
        if len(decisions) >= limit:
            break

    return {"decisions": decisions, "query": query}
