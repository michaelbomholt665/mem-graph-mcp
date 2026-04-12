"""
tools/notes.py — Free-form note creation, search, and listing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from pydantic import Field

from ..db import get_conn
from ..embeddings import embed

mcp = FastMCP("notes")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


@mcp.tool(tags={"namespace:note"})
async def note_create(
    content: Annotated[str, Field(description="Note body / content")],
    kind: Annotated[
        str,
        Field(description="Note kind: general | finding | warning | lesson | audit"),
    ] = "general",
    project_id: Annotated[
        str | None, Field(description="Project to associate this note with")
    ] = None,
    tags: Annotated[
        list[str] | None, Field(description="Optional list of tag strings")
    ] = None,
) -> dict:
    """
    Create a free-form note.

    Embeds the content for semantic search.
    Optionally links to a project and applies tags.
    Returns the new note_id.
    """
    conn = get_conn()
    note_id = _new_id()
    vec = await embed(content)
    tag_list: list[str] = tags or []

    conn.execute(
        """
        CREATE (n:Note {
            id: $id,
            kind: $kind,
            body: $body,
            tags: $tags,
            embedding: $embedding,
            created_at: $ts
        })
        """,
        {
            "id": note_id,
            "kind": kind,
            "body": content,
            "tags": tag_list,
            "embedding": vec,
            "ts": _now(),
        },
    )

    if project_id:
        conn.execute(
            """
            MATCH (p:Project {id: $project_id}), (n:Note {id: $note_id})
            CREATE (p)-[:HAS_NOTE]->(n)
            """,
            {"project_id": project_id, "note_id": note_id},
        )

    # Create Tag nodes and TAGGED relationships
    for tag in tag_list:
        conn.execute(
            """
            MERGE (t:Tag {name: $tag})
            WITH t
            MATCH (n:Note {id: $note_id})
            MERGE (n)-[:TAGGED]->(t)
            """,
            {"tag": tag, "note_id": note_id},
        )

    return {"note_id": note_id}


@mcp.tool(tags={"namespace:note"})
async def note_search(
    query: Annotated[str, Field(description="Natural language search query")],
    kind: Annotated[str | None, Field(description="Filter by note kind")] = None,
    project_id: Annotated[str | None, Field(description="Scope to a project")] = None,
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=20)] = 10,
) -> dict:
    """Semantic search over notes by content similarity."""
    conn = get_conn()
    vec = await embed(query)

    result = conn.execute(
        f"""
        CALL QUERY_VECTOR_INDEX('Note', 'idx_note_emb', $qvec, {limit * 3})
        WITH node AS n, distance
        OPTIONAL MATCH (p:Project)-[:HAS_NOTE]->(n)
        RETURN n.id, n.kind, n.body, n.tags, p.id AS project_id, distance
        ORDER BY distance
        LIMIT {limit * 3}
        """,
        {"qvec": vec},
    )

    notes: list[dict[str, Any]] = []
    for r in cast(list[list[Any]], result):
        if kind and r[1] != kind:
            continue
        if project_id and r[4] != project_id:
            continue
        notes.append(
            {
                "id": r[0],
                "kind": r[1],
                "body": r[2],
                "tags": r[3],
                "project_id": r[4],
                "distance": r[5],
            }
        )
        if len(notes) >= limit:
            break

    return {"notes": notes, "query": query}


@mcp.tool(tags={"namespace:note"})
async def note_list(
    project_id: Annotated[str | None, Field(description="Filter by project")] = None,
    kind: Annotated[str | None, Field(description="Filter by note kind")] = None,
) -> dict:
    """List notes without semantic ranking."""
    conn = get_conn()

    if project_id:
        result = conn.execute(
            """
            MATCH (p:Project {id: $project_id})-[:HAS_NOTE]->(n:Note)
            RETURN n.id, n.kind, n.body, n.tags, n.created_at
            ORDER BY n.created_at DESC
            """,
            {"project_id": project_id},
        )
    else:
        result = conn.execute(
            """
            MATCH (n:Note)
            RETURN n.id, n.kind, n.body, n.tags, n.created_at
            ORDER BY n.created_at DESC
            """,
        )

    notes = [
        {
            "id": r[0],
            "kind": r[1],
            "body": r[2],
            "tags": r[3],
            "created_at": str(r[4]),
        }
        for r in cast(list[list[Any]], result)
        if kind is None or r[1] == kind
    ]

    return {"notes": notes}
