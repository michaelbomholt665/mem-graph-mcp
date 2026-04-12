"""
tools/memory.py — Distilled memory store and semantic recall.

``memory_recall`` is the workhorse: embeds the query, runs QUERY_VECTOR_INDEX
against the Memory table, returns top-k results with cosine distance scores.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from pydantic import Field

from ..db import get_conn
from ..embeddings import embed

mcp = FastMCP("memory")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


@mcp.tool()
async def memory_store(
    content: Annotated[str, Field(description="The memory content to store")],
    kind: Annotated[
        str,
        Field(
            description="Memory kind: fact | preference | pattern | violation | architecture"
        ),
    ] = "fact",
    scope: Annotated[
        str,
        Field(description="Memory scope: global | project | backend | task"),
    ] = "global",
    project_id: Annotated[
        str | None, Field(description="Project ID to associate this memory with")
    ] = None,
) -> dict:
    """
    Store a distilled memory (fact, preference, pattern, etc.).

    Embeds the content and writes a Memory node.  If project_id is provided,
    links it via PROJECT_MEMORY.  Returns the new memory_id.
    """
    conn = get_conn()
    mem_id = _new_id()
    vec = await embed(content)

    conn.execute(
        """
        CREATE (m:Memory {
            id: $id,
            kind: $kind,
            scope: $scope,
            content: $content,
            confidence: 1.0,
            embedding: $embedding,
            created_at: $ts,
            updated_at: $ts
        })
        """,
        {
            "id": mem_id,
            "kind": kind,
            "scope": scope,
            "content": content,
            "embedding": vec,
            "ts": _now(),
        },
    )

    if project_id:
        conn.execute(
            """
            MATCH (p:Project {id: $project_id}), (m:Memory {id: $mem_id})
            CREATE (p)-[:PROJECT_MEMORY]->(m)
            """,
            {"project_id": project_id, "mem_id": mem_id},
        )

    return {"memory_id": mem_id}


@mcp.tool()
async def memory_recall(
    query: Annotated[
        str, Field(description="Natural language query for semantic search")
    ],
    scope: Annotated[
        str | None,
        Field(description="Filter by scope: global | project | backend | task"),
    ] = None,
    project_id: Annotated[
        str | None, Field(description="Filter to memories scoped to this project")
    ] = None,
    limit: Annotated[
        int, Field(description="Maximum results to return", ge=1, le=50)
    ] = 10,
) -> dict:
    """
    Semantic recall: embed the query and search Memory by cosine similarity.

    Ignores expired memories.  Optionally filter by scope or project.
    Returns memories ranked by relevance with distance scores.
    """
    conn = get_conn()
    vec = await embed(query)

    # QUERY_VECTOR_INDEX returns (node, distance)
    result = conn.execute(
        f"""
        CALL QUERY_VECTOR_INDEX('Memory', 'idx_memory_emb', $qvec, {limit * 3})
        WITH node AS m, distance
        WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
        OPTIONAL MATCH (m)<-[:PROJECT_MEMORY]-(p:Project)
        RETURN m.id, m.kind, m.scope, m.content, m.confidence, p.name AS project, distance
        ORDER BY distance
        LIMIT {limit}
        """,
        {"qvec": vec},
    )

    memories: list[dict[str, Any]] = []
    for row in cast(list[list[Any]], result):
        mem = {
            "id": row[0],
            "kind": row[1],
            "scope": row[2],
            "content": row[3],
            "confidence": row[4],
            "project": row[5],
            "distance": row[6],
        }
        # Apply optional filters in Python (Ladybug vector index doesn't support
        # arbitrary WHERE on node props before the result set is returned)
        if scope and mem["scope"] != scope:
            continue
        if project_id and mem["project"] is None:
            continue
        memories.append(mem)

    return {"memories": memories[:limit], "query": query}


@mcp.tool()
async def memory_search(
    query: Annotated[str, Field(description="Search query (cross-scope)")],
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=50)] = 10,
) -> dict:
    """
    Cross-scope semantic search across all Memory nodes regardless of scope or project.
    """
    conn = get_conn()
    vec = await embed(query)

    result = conn.execute(
        f"""
        CALL QUERY_VECTOR_INDEX('Memory', 'idx_memory_emb', $qvec, {limit})
        WITH node AS m, distance
        WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
        OPTIONAL MATCH (m)<-[:PROJECT_MEMORY]-(p:Project)
        RETURN m.id, m.kind, m.scope, m.content, m.confidence, p.name AS project, distance
        ORDER BY distance
        LIMIT {limit}
        """,
        {"qvec": vec},
    )

    memories = [
        {
            "id": row[0],
            "kind": row[1],
            "scope": row[2],
            "content": row[3],
            "confidence": row[4],
            "project": row[5],
            "distance": row[6],
        }
        for row in cast(list[list[Any]], result)
    ]

    return {"memories": memories, "query": query}


@mcp.tool(tags={"namespace:memory"})
async def memory_expire(
    memory_id: Annotated[str, Field(description="ID of the memory to expire")],
) -> dict:
    """
    Expire a memory by setting expires_at to now.

    Expired memories are excluded from recall results but are not deleted,
    preserving the historical record.
    """
    conn = get_conn()
    conn.execute(
        """
        MATCH (m:Memory {id: $id})
        SET m.expires_at = $ts, m.updated_at = $ts
        """,
        {"id": memory_id, "ts": _now()},
    )
    return {"memory_id": memory_id, "status": "expired"}


@mcp.tool(tags={"namespace:memory"})
async def memory_list(
    scope: Annotated[str | None, Field(description="Filter by scope")] = None,
    project_id: Annotated[str | None, Field(description="Filter by project ID")] = None,
) -> dict:
    """
    List memories without semantic ranking.  Useful for browsing.

    Excludes expired memories.
    """
    conn = get_conn()

    if project_id:
        result = conn.execute(
            """
            MATCH (p:Project {id: $project_id})-[:PROJECT_MEMORY]->(m:Memory)
            WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
            RETURN m.id, m.kind, m.scope, m.content, m.confidence, m.created_at
            ORDER BY m.created_at DESC
            """,
            {"project_id": project_id},
        )
    else:
        result = conn.execute(
            """
            MATCH (m:Memory)
            WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
            RETURN m.id, m.kind, m.scope, m.content, m.confidence, m.created_at
            ORDER BY m.created_at DESC
            """,
        )

    memories = [
        {
            "id": row[0],
            "kind": row[1],
            "scope": row[2],
            "content": row[3],
            "confidence": row[4],
            "created_at": str(row[5]),
        }
        for row in cast(list[list[Any]], result)
        if scope is None or row[2] == scope
    ]

    return {"memories": memories}
