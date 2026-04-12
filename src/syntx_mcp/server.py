"""
server.py — FastMCP app definition + lifespan wiring.

Each tool module exposes a ``mcp`` FastMCP sub-server that is mounted into
the root app via ``mcp.mount()``.
The server runs HTTP on MCP_HOST:MCP_PORT (default 127.0.0.1:9100).

Dynamic tool discovery
----------------------
Tools are split into two tiers:

  Core (always visible, 9 tools):
    memory_store, memory_recall, memory_search,
    decision_record, decision_search,
    task_search, task_update,
    project_search,
    tools_activate  ← this gateway tool

  Lazy namespaces (hidden until activated per-session):
    conversation, decision, task, project, memory, note, violation

Call ``tools_activate(namespace="<name>")`` to unlock a namespace for the
current session.  FastMCP will send a ToolListChangedNotification
automatically so the client's tool list updates live.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncGenerator, Literal, cast

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field
from fastmcp.providers.skills import SkillsDirectoryProvider  # type: ignore
import anyio
from anyio import to_thread
import uvicorn
from starlette.applications import Starlette

from .db import close_db, init_db
from .tools import (
    audit,
    conversation,
    decisions,
    memory,
    notes,
    projects,
    tasks,
    violations,
)

load_dotenv()

_HOST = os.getenv("MCP_HOST", "127.0.0.1")
_PORT = int(os.getenv("MCP_PORT", "9100"))

# All namespaces that are lazily hidden by default.
_LAZY_NAMESPACES: frozenset[str] = frozenset(
    {
        "conversation",
        "decision",
        "task",
        "project",
        "memory",
        "note",
        "violation",
        "audit",
    }
)


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncGenerator[None, None]:  # noqa: ARG001
    await to_thread.run_sync(init_db)
    yield
    await to_thread.run_sync(close_db)


mcp = FastMCP(
    "syntx-memory",
    instructions=(
        "Agent memory store for Syntx. "
        "Captures conversations, tasks, decisions, notes, violations "
        "and enables semantic recall across sessions.\n\n"
        "TOOL DISCOVERY: Only core tools are visible at startup. "
        "Call tools_activate(namespace=<name>) to unlock a group of "
        "specialised tools for your current session. "
        "Available namespaces: conversation, decision, task, project, "
        "memory, note, violation."
    ),
    lifespan=lifespan,
)


# Mount all tool sub-servers (FastMCP 3.x API)
mcp.mount(conversation.mcp)
mcp.mount(memory.mcp)
mcp.mount(projects.mcp)
mcp.mount(tasks.mcp)
mcp.mount(decisions.mcp)
mcp.mount(notes.mcp)
mcp.mount(violations.mcp)
mcp.mount(audit.mcp)

# Register the skills directory as a provider
mcp.add_provider(SkillsDirectoryProvider("skills"))


def _score_tool(tool_def: Any, query: str) -> int:
    tool_name = tool_def.name
    if tool_name in ["tools_activate", "tools_search"]:
        return 0
    desc = (tool_def.description or "").lower()
    name = tool_name.lower()
    score = 0
    if query in name:
        score += 10
    if query in desc:
        score += 5
    if score == 0:
        query_words = set(query.split())
        name_words = set(name.replace("_", " ").split())
        desc_words = set(desc.split())
        score += len(query_words.intersection(name_words)) * 3
        score += len(query_words.intersection(desc_words)) * 1
    return score

def _get_namespace(tool_def: Any) -> str:
    tags = getattr(tool_def, "tags", [])
    if tags:
        for tag in tags:
            if tag.startswith("namespace:"):
                return tag.replace("namespace:", "")
    return "core"

@mcp.tool()
async def tools_search(
    query: Annotated[
        str, Field(description="Search for tools by functionality, goal, or name")
    ],
) -> dict:
    """
    Search the full tool catalog to discover capabilities.

    If you're unsure which tool to use or which namespace to activate,
    call this first with a query like "task management" or "conversation storage".

    Returns a ranked list of tool candidates, their purpose, and the
    namespace name you should pass to tools_activate() to use them.
    """
    query = query.lower()
    results = []

    # Access the full catalog (including those currently disabled)
    # FastMCP (via AggregateProvider) exposes _list_tools() to get all underlying components
    all_tools = await mcp._list_tools()

    for tool_def in all_tools:
        score = _score_tool(tool_def, query)
        if score > 0:
            results.append(
                {
                    "tool": tool_def.name,
                    "description": tool_def.description or "No description provided.",
                    "namespace": _get_namespace(tool_def),
                    "score": score,
                }
            )

    # Sort by score descending and take top 10
    results.sort(key=lambda x: cast(int, x["score"]), reverse=True)
    top_results = results[:10]

    if not top_results:
        return {"message": f"No tools found matching {query!r}. Try broader keywords."}

    return {
        "results": [
            {
                "tool": r["tool"],
                "purpose": r["description"],
                "how_to_activate": f"Call tools_activate(namespace='{r['namespace']}')"
                if r["namespace"] != "core"
                else "Already active (core tool).",
            }
            for r in top_results
        ],
        "suggestion": (
            "Review the list above and call tools_activate(namespace='...') "
            "for the desired group."
        ),
    }


# ---------------------------------------------------------------------------
# Gateway tool — always visible, enables lazy namespaces per-session
# ---------------------------------------------------------------------------


@mcp.tool()
async def tools_activate(
    namespace: Annotated[
        str,
        Field(
            description=(
                "Namespace to activate for this session. "
                "One of: conversation, decision, task, project, memory, note, violation."
            )
        ),
    ],
    ctx: Context,
) -> dict:
    """
    Unlock a group of specialised tools for the current session.

    If you don't know which namespace to activate, call tools_search(query='...') first.

    Namespaces
    ----------
    conversation  — conversation_start/append/end/get
    decision      — decision_get, decision_supersede
    task          — task_create/get/block/link_decision/link_violation
    project       — project_create/get/list
    memory        — memory_expire, memory_list
    note          — note_create/search/list
    violation     — violation_record/resolve/recur/search/list
    audit         — audit_package
    """
    if namespace not in _LAZY_NAMESPACES:
        return {
            "error": (
                f"Unknown namespace {namespace!r}. "
                f"Choose from: {sorted(_LAZY_NAMESPACES)}"
            )
        }
    await ctx.enable_components(tags={f"namespace:{namespace}"}, components={"tool"})
    return {"activated": namespace, "status": "ok"}


# ---------------------------------------------------------------------------
# Globally hide all lazy namespaces — activated per-session via tools_activate
# ---------------------------------------------------------------------------

mcp.disable(tags={f"namespace:{ns}" for ns in _LAZY_NAMESPACES})


_TRANSPORT = os.getenv("MCP_TRANSPORT", "http")


def run() -> None:
    if _TRANSPORT == "stdio":
        mcp.run(transport="stdio")
    elif _TRANSPORT == "http":
        # Launching both streamable HTTP (Codex) and SSE (Anthropic Inspector)
        app_http = mcp.http_app(transport="streamable-http", path="/mcp")
        app_sse = mcp.http_app(transport="sse", path="/sse")

        @asynccontextmanager
        async def combined_lifespan(app_instance: Starlette) -> AsyncGenerator[None, None]:
            async with app_http.router.lifespan_context(app_instance):
                async with app_sse.router.lifespan_context(app_instance):
                    yield

        app = Starlette(
            routes=app_http.router.routes + app_sse.router.routes,
            lifespan=combined_lifespan,
        )

        async def serve() -> None:
            config = uvicorn.Config(
                app,
                host=_HOST,
                port=_PORT,
                lifespan="on",
                ws="websockets-sansio",
                log_level="info",
            )
            print(
                f"Starting MCP server {mcp.name!r} with protocols (HTTP: /mcp, SSE: /sse) on http://{_HOST}:{_PORT}",
                file=sys.stderr,
            )
            server = uvicorn.Server(config)
            await server.serve()

        anyio.run(serve)
    else:
        mcp.run(
            transport=cast(
                Literal["stdio", "http", "sse", "streamable-http"], _TRANSPORT
            ),
            host=_HOST,
            port=_PORT,
        )
