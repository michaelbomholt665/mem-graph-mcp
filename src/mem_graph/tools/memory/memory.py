"""
tools/memory/memory.py — Distilled memory store, semantic recall, and management.

Three tools form the complete memory surface:

  memory_store    — persist and store a distilled fact, pattern, or preference
  memory_manage   — expire outdated memories or list active ones
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from pydantic import Field

from ...db import get_conn
from ...embeddings import embed
from ...ids import new_id

logger = logging.getLogger(__name__)
mcp = FastMCP("memory")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@mcp.tool(tags={"namespace:memory"})
async def memory_store(
    content: Annotated[str, Field(description="The fact, pattern, or preference to remember")],
    kind: Annotated[
        str,
        Field(description="What type of memory this is: fact | preference | pattern | violation | architecture"),
    ] = "fact",
    scope: Annotated[
        str,
        Field(description="How broadly this applies: global | project | backend | task"),
    ] = "global",
    project_id: Annotated[
        str | None, Field(description="Associate with a specific project (optional)")
    ] = None,
) -> dict[str, str]:
    """
    Persist and store a distilled memory, fact, preference, or architectural pattern for future recall.

    Use this to save anything that should persist beyond the current conversation:
    facts, preferences, recurring patterns, or architectural decisions. Provide the
    content and categorise it with kind and scope. Returns the new memory ID.
    """
    conn = get_conn()
    mem_id = new_id()
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

    logger.info("Stored memory %s (kind=%s, scope=%s)", mem_id, kind, scope)
    return {"memory_id": mem_id}


@mcp.tool(tags={"namespace:memory"})
async def memory_manage(
    action: Annotated[
        str,
        Field(description="What to do: expire | list"),
    ],
    memory_id: Annotated[
        str | None,
        Field(description="Memory ID — required for action='expire'"),
    ] = None,
    scope: Annotated[
        str | None,
        Field(description="Filter by scope when action='list': global | project | backend | task"),
    ] = None,
    project_id: Annotated[
        str | None,
        Field(description="Filter to a specific project when action='list'"),
    ] = None,
) -> dict[str, Any]:
    """
    Manage stored memories: expire outdated facts or list and browse what's saved.

    Use action='expire' with a memory_id to soft-delete a fact that is no
    longer accurate. Use action='list' to browse active memories, optionally
    filtered by scope or project. Returns the operation result or memory list.
    """
    conn = get_conn()

    if action == "expire":
        if not memory_id:
            return {"error": "memory_id is required for action='expire'"}
        conn.execute(
            """
            MATCH (m:Memory {id: $id})
            SET m.expires_at = $ts, m.updated_at = $ts
            """,
            {"id": memory_id, "ts": _now()},
        )
        logger.info("Expired memory %s", memory_id)
        return {"memory_id": memory_id, "status": "expired"}

    if action == "list":
        return _list_memories(conn, scope, project_id)

    return {"error": f"Unknown action {action!r}. Use 'expire' or 'list'."}


def _list_memories(conn: Any, scope: str | None, project_id: str | None) -> dict[str, Any]:
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
