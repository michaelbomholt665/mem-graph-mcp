"""
tools/memory/memory.py — Distilled memory store, semantic recall, and management.

Three tools form the complete memory surface:

  memory_store    — persist and store a distilled fact, pattern, or preference
  memory_manage   — expire outdated memories or list active ones

FastMCP 3.0 upgrades:
- ``Depends(db_get_connection)`` injects the DB connection.
- ``ctx.elicit()`` requests confirmation before expiring a memory.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context
from mcp.types import Icon
from pydantic import Field

from ..markers import tier_2_tool

from ...db import db_get_connection
from ...observability import traced_tool
from ...services.memory import MemoryService

logger = logging.getLogger(__name__)
mcp = FastMCP("memory")


@tier_2_tool
@mcp.tool(
    tags={"namespace:memory"},
    icons=[
        Icon(
            src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0Ij48cGF0aCBkPSJNMTkgM0g1Yy0xLjEgMC0yIC45LTIgMnYxNGMwIDEuMS45IDIgMiAyaDE0YzEuMSAwIDItLjkgMi0yVjVjMC0xLjEtLjktMi0yLTJ6bTAgMTZINVY1aDE0djE0em0tMi1xIDIgMGg2VjExaC0zdi41aDAyaC0zczB2MWgzVjloLTZ6bS0yIDB2LTNoLTZ6bS00LTJoMnYyaC0yeiIvPjwvc3ZnPg==",
            mimeType="image/svg+xml",
        )
    ],
)
@traced_tool("memory_store")
async def memory_store(
    content: Annotated[
        str, Field(description="The fact, pattern, or preference to remember")
    ],
    kind: Annotated[
        str,
        Field(
            description="What type of memory this is: fact | preference | pattern | violation | architecture"
        ),
    ] = "fact",
    scope: Annotated[
        str,
        Field(
            description="How broadly this applies: global | project | backend | task"
        ),
    ] = "global",
    project_id: Annotated[
        str | None, Field(description="Associate with a specific project (optional)")
    ] = None,
    conn: Any = Depends(db_get_connection),
) -> dict[str, str]:
    """Store a memory for later recall."""
    service = MemoryService(conn)
    memory_id = await service.store(
        content=content,
        kind=kind,
        scope=scope,
        project_id=project_id,
    )
    logger.info("Stored memory %s (kind=%s, scope=%s)", memory_id, kind, scope)
    return {"memory_id": memory_id}


@tier_2_tool
@mcp.tool(
    tags={"namespace:memory"},
    icons=[
        Icon(
            src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0Ij48cGF0aCBkPSJNMTkgNkg1Yy0xLjEgMC0yIC45LTIgMnYxMGMwIDEuMS45IDIgMiAyaDE0YzEuMSAwIDItLjkgMi0yVjhj MC0xLjEtLjktMi0yLTJ6bTAgMTJINVY4aDE0djEweiIvPjwvc3ZnPg==",
            mimeType="image/svg+xml",
        )
    ],
)
@traced_tool("memory_manage")
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
        Field(
            description="Filter by scope when action='list': global | project | backend | task"
        ),
    ] = None,
    project_id: Annotated[
        str | None,
        Field(description="Filter to a specific project when action='list'"),
    ] = None,
    conn: Any = Depends(db_get_connection),
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Expire or list stored memories by scope or project."""
    if action == "expire":
        if not memory_id:
            return {"error": "memory_id is required for action='expire'"}

        # Elicit confirmation for destructive operations
        if ctx is not None:
            try:
                from fastmcp.server.elicitation import AcceptedElicitation

                confirmation = await ctx.elicit(
                    message=f"Are you sure you want to expire memory {memory_id!r}? This cannot be undone.",
                    response_type=["yes", "no"],  # type: ignore[arg-type]
                )
                if (
                    not isinstance(confirmation, AcceptedElicitation)
                    or confirmation.data != "yes"
                ):
                    return {
                        "memory_id": memory_id,
                        "status": "cancelled",
                        "reason": "User did not confirm.",
                    }
            except Exception as exc:
                logger.warning(
                    "Elicitation unavailable; blocking destructive operation: %s", exc
                )
                return {
                    "memory_id": memory_id,
                    "status": "cancelled",
                    "reason": "Confirmation unavailable; expiry blocked for safety.",
                }

        service = MemoryService(conn)
        logger.info("Expired memory %s", memory_id)
        return service.expire(memory_id)

    if action == "list":
        service = MemoryService(conn)
        return {"memories": service.list_active(scope=scope, project_id=project_id)}

    return {"error": f"Unknown action {action!r}. Use 'expire' or 'list'."}
