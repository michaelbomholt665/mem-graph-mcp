"""
tools/work/projects.py — Project management tools.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from pydantic import Field

from ...db import db_get_connection
from ...embeddings import embeddings_generate
from ...ids import id_generate_v7

mcp = FastMCP("projects")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@mcp.tool(tags={"namespace:work"})
async def project_create(
    name: Annotated[str, Field(description="Project name")],
    description: Annotated[str, Field(description="Project description")],
    repo_path: Annotated[
        str | None, Field(description="Path to the repository root")
    ] = None,
) -> dict:
    """
    Register and create a new project as the top-level context for work tracking.

    Provide a name and description — the project will be indexed for semantic search.
    Returns a project_id to use when creating tasks, decisions, and capturing sessions.
    """
    conn = db_get_connection()
    project_id = id_generate_v7()
    vec = await embeddings_generate(f"{name}\n{description}")

    conn.execute(
        """
        CREATE (p:Project {
            id: $id,
            name: $name,
            description: $description,
            status: 'active',
            repo_path: $repo_path,
            embedding: $embedding,
            created_at: $ts,
            updated_at: $ts
        })
        """,
        {
            "id": project_id,
            "name": name,
            "description": description,
            "repo_path": repo_path or "",
            "embedding": vec,
            "ts": _now(),
        },
    )

    return {"project_id": project_id}


@mcp.tool(tags={"namespace:work"})
async def project_get(
    project_id: Annotated[str, Field(description="Project ID to retrieve")],
) -> dict:
    """Retrieve full details for a project by its ID. Returns name, description, status, and creation timestamps."""
    conn = db_get_connection()
    result = conn.execute(
        """
        MATCH (p:Project {id: $id})
        RETURN p.id, p.name, p.description, p.status, p.repo_path, p.created_at, p.updated_at
        """,
        {"id": project_id},
    )
    if isinstance(result, list):
        result = result[0]
    rows = cast(list[list[Any]], result.get_all())
    if not rows:
        return {"error": f"Project {project_id!r} not found"}
    r = rows[0]
    return {
        "project": {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "status": r[3],
            "repo_path": r[4],
            "created_at": str(r[5]),
            "updated_at": str(r[6]),
        }
    }


@mcp.tool(tags={"namespace:work"})
async def project_list() -> dict:
    """List and browse all registered projects. Returns names, statuses, and IDs — useful to find a project_id before doing more specific work."""
    conn = db_get_connection()
    result = conn.execute(
        """
        MATCH (p:Project)
        RETURN p.id, p.name, p.description, p.status, p.created_at
        ORDER BY p.created_at DESC
        """,
    )
    if isinstance(result, list):
        result = result[0]
    projects = [
        {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "status": r[3],
            "created_at": str(r[4]),
        }
        for r in cast(list[list[Any]], result.get_all())
    ]
    return {"projects": projects}


@mcp.tool()
async def project_search(
    query: Annotated[
        str, Field(description="Natural language query for semantic project search")
    ],
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=20)] = 5,
) -> dict:
    """Find and retrieve projects semantically similar to a search query. Provide a description of the work you're doing and get back the most relevant project IDs."""
    conn = db_get_connection()
    vec = await embeddings_generate(query)

    result = conn.execute(
        """
        CALL QUERY_VECTOR_INDEX('Project', 'idx_project_emb', $qvec, $limit)
        WITH node AS p, distance
        RETURN p.id, p.name, p.description, p.status, distance
        ORDER BY distance
        LIMIT $limit
        """,
        {"qvec": vec, "limit": limit},
    )

    if isinstance(result, list):
        result = result[0]

    projects = [
        {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "status": r[3],
            "distance": r[4],
        }
        for r in cast(list[list[Any]], result.get_all())
    ]
    return {"projects": projects, "query": query}
