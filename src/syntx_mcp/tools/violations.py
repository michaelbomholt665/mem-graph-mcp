"""
tools/violations.py — Audit violation lifecycle tools.

Supports the full violation lifecycle:
  open → resolved
  open → recurrence (re-opened with a new node linked via VIOLATION_RECURS)
  open → graduated (promoted to a tracked task)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from pydantic import Field

from ..db import get_conn
from ..embeddings import embed

mcp = FastMCP("violations")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


@mcp.tool(tags={"namespace:violation"})
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
    Record a new audit violation.

    Embeds the description for semantic search.
    Links to project (and optionally backend) via relationship.
    Returns the new violation_id.
    """
    conn = get_conn()
    violation_id = _new_id()
    text = f"{rule} {severity} {file_path}\n{description}"
    vec = await embed(text)
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


@mcp.tool(tags={"namespace:violation"})
async def violation_resolve(
    violation_id: Annotated[str, Field(description="Violation ID to mark as resolved")],
) -> dict:
    """
    Mark a violation as resolved.

    Sets status to 'resolved' and records resolved_at timestamp.
    """
    conn = get_conn()
    ts = _now()
    conn.execute(
        """
        MATCH (v:Violation {id: $id})
        SET v.status = 'resolved', v.resolved_at = $ts
        """,
        {"id": violation_id, "ts": ts},
    )
    return {"violation_id": violation_id, "status": "resolved"}


@mcp.tool(tags={"namespace:violation"})
async def violation_recur(
    original_id: Annotated[
        str, Field(description="ID of the original violation that recurred")
    ],
    new_description: Annotated[str, Field(description="Description of the recurrence")],
) -> dict:
    """
    Record a recurrence of a previously seen violation.

    Creates a new Violation node with status 'recurrence', links it to the
    original via VIOLATION_RECURS, and inherits project + audit context.
    Returns the new violation_id.
    """
    conn = get_conn()

    # Fetch original violation context
    result = conn.execute(
        """
        MATCH (v:Violation {id: $id})
        RETURN v.audit_id, v.rule, v.severity, v.file_path
        """,
        {"id": original_id},
    )
    rows = cast(list[list[Any]], result)
    if not rows:
        return {"error": f"Violation {original_id!r} not found"}

    orig = rows[0]
    audit_id, rule, severity, file_path = orig[0], orig[1], orig[2], orig[3]

    new_id = _new_id()
    text = f"{rule} {severity} {file_path}\n{new_description}"
    vec = await embed(text)
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
            "id": new_id,
            "audit_id": audit_id,
            "rule": rule,
            "severity": severity,
            "file_path": file_path,
            "description": new_description,
            "embedding": vec,
            "ts": ts,
        },
    )

    # Link original → recurrence
    conn.execute(
        """
        MATCH (orig:Violation {id: $orig_id}), (new_v:Violation {id: $new_id})
        CREATE (orig)-[:VIOLATION_RECURS {detected_at: $ts}]->(new_v)
        """,
        {"orig_id": original_id, "new_id": new_id, "ts": ts},
    )

    # Copy project relationship
    conn.execute(
        """
        MATCH (p:Project)-[:HAS_VIOLATION]->(orig:Violation {id: $orig_id})
        MATCH (new_v:Violation {id: $new_id})
        CREATE (p)-[:HAS_VIOLATION]->(new_v)
        """,
        {"orig_id": original_id, "new_id": new_id},
    )

    return {"violation_id": new_id, "original_id": original_id}


@mcp.tool(tags={"namespace:violation"})
async def violation_search(
    query: Annotated[str, Field(description="Natural language search query")],
    project_id: Annotated[str | None, Field(description="Scope to a project")] = None,
    status: Annotated[
        str | None,
        Field(description="Filter by status: open | recurrence | resolved | graduated"),
    ] = None,
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=20)] = 10,
) -> dict:
    """Semantic search over violations by description similarity."""
    conn = get_conn()
    vec = await embed(query)

    result = conn.execute(
        f"""
        CALL QUERY_VECTOR_INDEX('Violation', 'idx_violation_emb', $qvec, {limit * 3})
        WITH node AS v, distance
        OPTIONAL MATCH (p:Project)-[:HAS_VIOLATION]->(v)
        RETURN v.id, v.rule, v.severity, v.status, v.file_path, p.id AS project_id, distance
        ORDER BY distance
        LIMIT {limit * 3}
        """,
        {"qvec": vec},
    )

    violations: list[dict[str, Any]] = []
    for r in cast(list[list[Any]], result):
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
                "distance": r[6],
            }
        )
        if len(violations) >= limit:
            break

    return {"violations": violations, "query": query}


@mcp.tool(tags={"namespace:violation"})
async def violation_list(
    project_id: Annotated[str | None, Field(description="Filter by project")] = None,
    status: Annotated[str | None, Field(description="Filter by status")] = None,
) -> dict:
    """List violations without semantic ranking."""
    conn = get_conn()

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
