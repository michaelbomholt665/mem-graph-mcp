"""
tools/projects.py — Project node management tools.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from pydantic import Field

from ..db import get_conn
from ..embeddings import embed

mcp = FastMCP("projects")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


@mcp.tool(tags={"namespace:project"})
async def project_create(
    name: Annotated[str, Field(description="Project name")],
    description: Annotated[str, Field(description="Project description")],
    repo_path: Annotated[
        str | None, Field(description="Path to the repository root")
    ] = None,
) -> dict:
    """
    Create a new project.

    Embeds the description for later semantic search.
    Returns the new project_id.
    """
    conn = get_conn()
    project_id = _new_id()
    vec = await embed(f"{name}\n{description}")

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


@mcp.tool(tags={"namespace:project"})
async def project_get(
    project_id: Annotated[str, Field(description="Project ID to retrieve")],
) -> dict:
    """Return a project node by ID."""
    conn = get_conn()
    result = conn.execute(
        """
        MATCH (p:Project {id: $id})
        RETURN p.id, p.name, p.description, p.status, p.repo_path, p.created_at, p.updated_at
        """,
        {"id": project_id},
    )
    rows = cast(list[list[Any]], result)
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


@mcp.tool(tags={"namespace:project"})
async def project_list() -> dict:
    """List all projects."""
    conn = get_conn()
    result = conn.execute(
        """
        MATCH (p:Project)
        RETURN p.id, p.name, p.description, p.status, p.created_at
        ORDER BY p.created_at DESC
        """,
    )
    projects = [
        {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "status": r[3],
            "created_at": str(r[4]),
        }
        for r in cast(list[list[Any]], result)
    ]
    return {"projects": projects}


@mcp.tool()
async def project_search(
    query: Annotated[
        str, Field(description="Natural language query for semantic project search")
    ],
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=20)] = 5,
) -> dict:
    """Semantic search over projects by description similarity."""
    conn = get_conn()
    vec = await embed(query)

    result = conn.execute(
        f"""
        CALL QUERY_VECTOR_INDEX('Project', 'idx_project_emb', $qvec, {limit})
        WITH node AS p, distance
        RETURN p.id, p.name, p.description, p.status, distance
        ORDER BY distance
        LIMIT {limit}
        """,
        {"qvec": vec},
    )

    projects = [
        {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "status": r[3],
            "distance": r[4],
        }
        for r in cast(list[list[Any]], result)
    ]
    return {"projects": projects, "query": query}
