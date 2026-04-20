"""
tools/memory/notes.py — Free-form note creation, search, and listing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from ..markers import tier_2_tool
from fastmcp.dependencies import Depends
from pydantic import Field

from ...db import db_get_connection
from ...embeddings import embeddings_generate
from ...ids import id_generate_v7
from ...services.search import rrf_fuse

mcp = FastMCP("notes")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@tier_2_tool
@mcp.tool(tags={"namespace:notes"})
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
    conn: Any = Depends(db_get_connection),
) -> dict:
    """Create a note for a project or global context."""
    if not hasattr(conn, "execute"):
        conn = db_get_connection()

    note_id = id_generate_v7()
    vec = await embeddings_generate(content)
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


@tier_2_tool
@mcp.tool(tags={"namespace:notes"})
async def note_search(
    query: Annotated[str, Field(description="Natural language search query")],
    kind: Annotated[str | None, Field(description="Filter by note kind")] = None,
    project_id: Annotated[str | None, Field(description="Scope to a project")] = None,
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=20)] = 10,
    conn: Any = Depends(db_get_connection),
) -> dict:
    """Search notes by semantic similarity."""
    vec = await embeddings_generate(query)
    candidate_size = limit * 3

    vector_raw = conn.execute(
        """
        CALL QUERY_VECTOR_INDEX('Note', 'idx_note_emb', $qvec, $candidate_size)
        WITH node AS n, distance
        OPTIONAL MATCH (p:Project)-[:HAS_NOTE]->(n)
        RETURN n.id, n.kind, n.body, n.tags, p.id AS project_id, distance
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
        CALL QUERY_FTS_INDEX('Note', 'fts_note_body', $q)
        WITH node AS n, score
        OPTIONAL MATCH (p:Project)-[:HAS_NOTE]->(n)
        RETURN n.id, n.kind, n.body, n.tags, p.id AS project_id, score
        ORDER BY score DESC
        LIMIT $candidate_size
        """,
        {"q": query, "candidate_size": candidate_size},
    )
    if isinstance(fts_raw, list):
        fts_raw = fts_raw[0]
    fts_rows = cast(list[list[Any]], fts_raw.get_all())

    vector_hits = [(row[0], float(row[5])) for row in vector_rows]
    fts_hits = [(row[0], float(rank)) for rank, row in enumerate(fts_rows, start=1)]
    ranks = dict(rrf_fuse(vector_hits, fts_hits))

    data_map: dict[str, list[Any]] = {row[0]: row for row in vector_rows}
    for row in fts_rows:
        data_map[row[0]] = row

    notes: list[dict[str, Any]] = []
    for node_id, _ in sorted(ranks.items(), key=lambda item: item[1], reverse=True):
        if node_id not in data_map:
            continue
        r = data_map[node_id]
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
                "distance": 1.0 - ranks[node_id],
            }
        )
        if len(notes) >= limit:
            break

    return {"notes": notes, "query": query}


@tier_2_tool
@mcp.tool(tags={"namespace:notes"})
async def note_list(
    project_id: Annotated[str | None, Field(description="Filter by project")] = None,
    kind: Annotated[str | None, Field(description="Filter by note kind")] = None,
    conn: Any = Depends(db_get_connection),
) -> dict:
    """List notes filtered by project or kind."""
    if not hasattr(conn, "execute"):
        conn = db_get_connection()

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
