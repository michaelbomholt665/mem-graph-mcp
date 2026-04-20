"""Operational tools for sandbox session inspection and cleanup."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from ..markers import hidden_tool
from pydantic import Field

from ...services.sandbox_sessions import sandbox_manager

mcp = FastMCP("sandbox", instructions="Sandbox session status and cleanup tools.")
_TAG = {"namespace:sandbox"}


@hidden_tool
async def sandbox_session_status(
    session_id: Annotated[str, Field(description="Sandbox session id.")],
) -> dict[str, Any]:
    manager = sandbox_manager()
    session = manager.get_session(session_id)
    return session.model_dump(mode="json")


@hidden_tool
async def sandbox_session_list() -> dict[str, Any]:
    manager = sandbox_manager()
    return {
        "sessions": [session.model_dump(mode="json") for session in manager.list_sessions()]
    }


@hidden_tool
async def sandbox_session_destroy(
    session_id: Annotated[str, Field(description="Sandbox session id to destroy.")],
) -> dict[str, Any]:
    manager = sandbox_manager()
    session = await manager.destroy_session(session_id)
    return session.model_dump(mode="json")
