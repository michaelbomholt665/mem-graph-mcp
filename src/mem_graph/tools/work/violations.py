"""
tools/work/violations.py — Audit violation lifecycle tools.

Supports the full violation lifecycle:
  open → resolved
  open → recurrence (re-opened with a new record linked to the original)
  open → graduated (promoted to a tracked task)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from pydantic import Field

from ...db import db_get_connection
from ...embeddings import embeddings_generate
from ...ids import id_generate_v7 as _new_id
from ...observability import traced_tool
from ...services.search import rrf_fuse

mcp = FastMCP("violations")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@mcp.tool(tags={"namespace:work"})
@traced_tool("violation_record")
async def violation_record(
    project_id: Annotated[str, Field(description="Owning project ID")],
    audit_id: Annotated[str, Field(description="Audit identifier, e.g. '002A'")],
    rule: Annotated[
        str, Field(description="Rule identifier, e.g. 'CWE-252' or 'custom:no-todo'")
    ],
    severity: Annotated[
        str,
        Field(description="Severity: info | minor | major | critical | blocker"),
    ],
    file_path: Annotated[
        str, Field(description="File path where the violation was detected")
    ],
    description: Annotated[str, Field(description="Detailed violation description")],
    backend_id: Annotated[
        str | None,
        Field(description="Optional backend ID to associate the violation with"),
    ] = None,
) -> dict:
    """
    Log and record a code quality or policy violation found during an audit run.

    Provide the project, audit ID, rule identifier, severity, file location, and
    description. Returns a violation_id for tracking and linking to tasks.
    """
    conn = db_get_connection()
    violation_id = _new_id()
    text = f"{rule} {severity} {file_path}\n{description}"
    vec = await embeddings_generate(text)
    ts = _now()

    conn.execute(
        """
        CREATE (v:Violation {
            id: $id,
            audit_id: $audit_id,
            rule: $rule,
            severity: $severity,
            file_path: $file_path,
            description: $description,
            status: 'open',
            embedding: $embedding,
            detected_at: $ts
        })
        """,
        {
            "id": violation_id,
            "audit_id": audit_id,
            "rule": rule,
            "severity": severity,
            "file_path": file_path,
            "description": description,
            "embedding": vec,
            "ts": ts,
        },
    )

    conn.execute(
        """
        MATCH (p:Project {id: $project_id}), (v:Violation {id: $violation_id})
        CREATE (p)-[:HAS_VIOLATION]->(v)
        """,
        {"project_id": project_id, "violation_id": violation_id},
    )

    if backend_id:
        conn.execute(
            """
            MATCH (b:Backend {id: $backend_id}), (v:Violation {id: $violation_id})
            CREATE (b)-[:BACKEND_VIOLATION]->(v)
            """,
            {"backend_id": backend_id, "violation_id": violation_id},
        )

    return {"violation_id": violation_id}


@mcp.tool(tags={"namespace:work"})
@traced_tool("violation_resolve")
async def violation_resolve(
    violation_id: Annotated[str, Field(description="Violation ID to mark as resolved")],
) -> dict:
    """
    Mark and close a violation as fixed and resolved.

    Provide the violation ID to close it out. The resolved timestamp is recorded
    so fix time can be tracked. Returns confirmation.
    """
    conn = db_get_connection()
    ts = _now()
    conn.execute(
        """
        MATCH (v:Violation {id: $id})
        SET v.status = 'resolved', v.resolved_at = $ts
        """,
        {"id": violation_id, "ts": ts},
    )
    return {"violation_id": violation_id, "status": "resolved"}


@mcp.tool(tags={"namespace:work"})
@traced_tool("violation_recur")
async def violation_recur(
    original_id: Annotated[
        str, Field(description="ID of the original violation that recurred")
    ],
    new_description: Annotated[str, Field(description="Description of the recurrence")],
) -> dict:
    """
    Record and track that a previously fixed violation has reappeared as a recurrence.

    Provide the original violation ID and a description of where it recurred.
    A new violation record is created and linked to the original for drift tracking.
    Returns the new violation_id.
    """
    conn = db_get_connection()

    result = conn.execute(
        """
        MATCH (v:Violation {id: $id})
        RETURN v.audit_id, v.rule, v.severity, v.file_path
        """,
        {"id": original_id},
    )
    if isinstance(result, list):
        result = result[0]
    rows = cast(list[list[Any]], result.get_all())
    if not rows:
        return {"error": f"Violation {original_id!r} not found"}

    orig = rows[0]
    audit_id, rule, severity, file_path = orig[0], orig[1], orig[2], orig[3]

    recurrence_id = _new_id()
    text = f"{rule} {severity} {file_path}\n{new_description}"
    vec = await embeddings_generate(text)
    ts = _now()

    conn.execute(
        """
        CREATE (v:Violation {
            id: $id,
            audit_id: $audit_id,
            rule: $rule,
            severity: $severity,
            file_path: $file_path,
            description: $description,
            status: 'recurrence',
            embedding: $embedding,
            detected_at: $ts
        })
        """,
        {
            "id": recurrence_id,
            "audit_id": audit_id,
            "rule": rule,
            "severity": severity,
            "file_path": file_path,
            "description": new_description,
            "embedding": vec,
            "ts": ts,
        },
    )

    conn.execute(
        """
        MATCH (orig:Violation {id: $orig_id}), (new_v:Violation {id: $new_id})
        CREATE (orig)-[:VIOLATION_RECURS {detected_at: $ts}]->(new_v)
        """,
        {"orig_id": original_id, "new_id": recurrence_id, "ts": ts},
    )

    conn.execute(
        """
        MATCH (p:Project)-[:HAS_VIOLATION]->(orig:Violation {id: $orig_id})
        MATCH (new_v:Violation {id: $new_id})
        CREATE (p)-[:HAS_VIOLATION]->(new_v)
        """,
        {"orig_id": original_id, "new_id": recurrence_id},
    )

    return {"violation_id": recurrence_id, "original_id": original_id}


@mcp.tool(tags={"namespace:work"})
@traced_tool("violation_search")
async def violation_search(
    query: Annotated[str, Field(description="Natural language search query")],
    project_id: Annotated[str | None, Field(description="Scope to a project")] = None,
    status: Annotated[
        str | None,
        Field(description="Filter by status: open | recurrence | resolved | graduated"),
    ] = None,
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=20)] = 10,
) -> dict:
    """Find and retrieve violations relevant to a pattern or file using semantic search. Optionally filter by project or status. Returns ranked violations."""
    conn = db_get_connection()
    vec = await embeddings_generate(query)
    candidate_size = limit * 3

    vector_raw = conn.execute(
        """
        CALL QUERY_VECTOR_INDEX('Violation', 'idx_violation_emb', $qvec, $candidate_size)
        WITH node AS v, distance
        OPTIONAL MATCH (p:Project)-[:HAS_VIOLATION]->(v)
        RETURN v.id, v.rule, v.severity, v.status, v.file_path, p.id AS project_id, distance
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
        CALL QUERY_FTS_INDEX('Violation', 'fts_violation_desc', $q)
        WITH node AS v, score
        OPTIONAL MATCH (p:Project)-[:HAS_VIOLATION]->(v)
        RETURN v.id, v.rule, v.severity, v.status, v.file_path, p.id AS project_id, score
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

    violations: list[dict[str, Any]] = []
    for node_id, _ in sorted(ranks.items(), key=lambda item: item[1], reverse=True):
        if node_id not in data_map:
            continue
        r = data_map[node_id]
        if project_id and r[5] != project_id:
            continue
        if status and r[3] != status:
            continue
        violations.append(
            {
                "id": r[0],
                "rule": r[1],
                "severity": r[2],
                "status": r[3],
                "file_path": r[4],
                "project_id": r[5],
                "distance": 1.0 - ranks[node_id],
            }
        )
        if len(violations) >= limit:
            break

    return {"violations": violations, "query": query}


@mcp.tool(tags={"namespace:work"})
@traced_tool("violation_list")
async def violation_list(
    project_id: Annotated[str | None, Field(description="Filter by project")] = None,
    status: Annotated[str | None, Field(description="Filter by status")] = None,
) -> dict:
    """Browse and list all violations without ranking. Filter by project or status to review the open audit backlog."""
    conn = db_get_connection()

    if project_id:
        result = conn.execute(
            """
            MATCH (p:Project {id: $project_id})-[:HAS_VIOLATION]->(v:Violation)
            RETURN v.id, v.audit_id, v.rule, v.severity, v.status, v.file_path, v.detected_at
            ORDER BY v.detected_at DESC
            """,
            {"project_id": project_id},
        )
    else:
        result = conn.execute(
            """
            MATCH (v:Violation)
            RETURN v.id, v.audit_id, v.rule, v.severity, v.status, v.file_path, v.detected_at
            ORDER BY v.detected_at DESC
            """,
        )

    violations = [
        {
            "id": r[0],
            "audit_id": r[1],
            "rule": r[2],
            "severity": r[3],
            "status": r[4],
            "file_path": r[5],
            "detected_at": str(r[6]),
        }
        for r in cast(list[list[Any]], result)
        if status is None or r[4] == status
    ]

    return {"violations": violations}
