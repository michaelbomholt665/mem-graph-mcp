"""
server.py — FastMCP app definition + lifespan wiring.

Each tool module exposes a ``mcp`` FastMCP sub-server that is mounted into
the root app via ``mcp.mount()``.
The server runs HTTP on MCP_HOST:MCP_PORT (default 127.0.0.1:9100).

CodeMode (Phase A)
------------------
The server uses FastMCP's CodeMode transform, which exposes three meta-tools
to the AI instead of the full catalog:
  - search_tools(query)   — BM25 over tool names and descriptions
  - inspect_tool(name)    — returns full schema for a specific tool
  - execute_code(code)    — runs generated Python that calls the real tools

Direct tool calls (non-CodeMode clients) continue to work unchanged.

Dynamic tool discovery
----------------------
Tools are split into two tiers:

  Core (always visible):
    memory_store, memory_recall, memory_capture_session, memory_annotate,
    memory_manage,
    decision_record, decision_search,
    task_search, task_update,
    project_search,
    tools_activate, tools_search

  Lazy namespaces (hidden until activated per-session):
    memory     — memory_store, memory_recall, memory_manage,
                 memory_capture_session, memory_annotate
    work       — task_*, decision_*, project_*, violation_*
    notes      — note_*
        audit      — audit_package, map_codebase, triage_violations, decision_review,
                                 orchestrate_codebase
    filesystem — file_read, file_write, file_edit, file_delete, file_search, file_grep
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncGenerator, Literal, cast

import anyio
from anyio import to_thread
import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.context import Context
from fastmcp.server.providers.skills import SkillsProvider  # type: ignore[import-untyped]
from fastmcp.experimental.transforms.code_mode import CodeMode  # type: ignore[import-untyped]
from pydantic import Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

from .auth import AUTH_ENABLED, ApiKeyMiddleware
from .db import close_db, get_conn, init_db
from .logging import configure_logging
from .providers.openapi import build_openapi_provider
from .services.summarizer import start_worker, stop_worker
from .resources.prompts import PROMPT_REGISTRY, get_sub_agent_instructions
from .tools import (
    audit,
    conversation,
    decisions,
    diagrams,
    filesystem,
    map as map_tool,
    memory,
    notes,
    orchestrator,
    projects,
    tasks,
    triage,
    violations,
)

load_dotenv()

# Pre-emptively set a dummy key to avoid pydantic-ai import-time crashes if no key is in .env.
# This allows the server to start even if agents aren't fully configured yet.
if not os.getenv("OPENAI_API_KEY"):
    os.environ.setdefault("OPENAI_API_KEY", "missing-key-set-in-env-file")



# (load_dotenv called at top of file)
configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_HOST = os.getenv("MCP_HOST", "127.0.0.1")
_PORT = int(os.getenv("MCP_PORT", "9100"))

# Consolidated namespaces
_LAZY_NAMESPACES: frozenset[str] = frozenset({"memory", "work", "notes", "audit", "filesystem"})

# Legacy namespace → canonical replacement
_DEPRECATED_NAMESPACES: dict[str, str] = {
    "conversation": "memory",
    "decision": "work",
    "task": "work",
    "project": "work",
    "violation": "work",
    "note": "notes",
}

# Comma-separated OpenAPI spec URLs (optional)
_OPENAPI_SPECS: list[str] = [
    s.strip()
    for s in os.getenv("MEM_GRAPH_OPENAPI_SPECS", "").split(",")
    if s.strip()
]


_BANNER = r"""
   _____             _             __  __                                
  / ____|           | |           |  \/  |                               
 | (___  _   _ _ __ | |_ __  __   | \  / | ___ _ __ ___   ___  _ __ _   _ 
  \___ \| | | | '_ \| __|\ \/ /   | |\/| |/ _ \ '_ ` _ \ / _ \| '__| | | |
  ____) | |_| | | | | |_  >  <    | |  | |  __/ | | | | | (_) | |  | |_| |
 |_____/ \__, |_| |_|\__|/_/\_\   |_|  |_|\___|_| |_| |_|\___/|_|   \__, |
          __/ |                                                      __/ |
         |___/                                                      |___/ 
"""


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncGenerator[None, None]:  # noqa: ARG001
    # Print banner before starting logging if possible, or just log it
    if sys.stderr.isatty():
        print(_BANNER, file=sys.stderr)
        print(f"  Version: 0.1.0 | CodeMode: ENABLED | Host: {_HOST}:{_PORT}\n", file=sys.stderr)

    await to_thread.run_sync(init_db)
    start_worker()
    await _load_openapi_providers()
    logger.info("mem-graph server ready.")
    yield
    await stop_worker()
    await to_thread.run_sync(close_db)
    logger.info("mem-graph server shut down cleanly.")


async def _load_openapi_providers() -> None:
    """Fetch and register OpenAPI providers from MEM_GRAPH_OPENAPI_SPECS (async, runs in lifespan)."""
    for spec_url in _OPENAPI_SPECS:
        try:
            provider = await build_openapi_provider(spec_url)
            mcp.add_provider(provider)
            logger.info("openapi_provider_loaded spec=%s", spec_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("openapi_provider_failed spec=%s error=%s", spec_url, exc)


mcp = FastMCP(
    "syntx-memory",
    instructions=(
        "Agent memory store for Syntx. "
        "Captures conversations, tasks, decisions, notes, violations "
        "and enables semantic recall across sessions.\n\n"
        "TOOL DISCOVERY: Only core tools are visible at startup. "
        "Call tools_activate(namespace=<name>) to unlock a group of "
        "specialised tools for your current session. "
        "Available namespaces: memory, work, notes, audit, filesystem.\n"
        "Call tools_search(query='...') if you're unsure which namespace to use."
    ),
    lifespan=lifespan,
    transforms=[CodeMode()],
)


# Mount all tool sub-servers
mcp.mount(conversation.mcp)
mcp.mount(memory.mcp)
mcp.mount(projects.mcp)
mcp.mount(tasks.mcp)
mcp.mount(decisions.mcp)
mcp.mount(notes.mcp)
mcp.mount(violations.mcp)
mcp.mount(audit.mcp)
mcp.mount(diagrams.mcp)
mcp.mount(map_tool.mcp)
mcp.mount(orchestrator.mcp)
mcp.mount(triage.mcp)
mcp.mount(filesystem.mcp)

# Skills directory provider — drop .py files into skills/ to add tools on restart
mcp.add_provider(SkillsProvider("skills"))

# (OpenAPI providers are loaded asynchronously in lifespan → _load_openapi_providers)


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
    Discover which tools and namespaces can help with your current goal.

    Describe what you want to accomplish in plain language. Returns a ranked list
    of matching tools and the namespace to activate to use them.
    """
    query = query.lower()
    results = []

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


@mcp.tool()
async def tools_activate(
    namespace: Annotated[
        str,
        Field(
            description=(
                "Namespace to activate for this session. "
                "One of: memory, work, notes, audit, filesystem."
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
    memory     — memory_capture_session, memory_recall, memory_annotate,
                 memory_store, memory_manage
    work       — task_*, decision_*, project_*, violation_*
    notes      — note_create, note_search, note_list
    audit      — audit_package, map_codebase, triage_violations, decision_review
    filesystem — file_read, file_write, file_edit, file_delete, file_search, file_grep
    """
    # Handle deprecated namespace aliases
    if namespace in _DEPRECATED_NAMESPACES:
        canonical = _DEPRECATED_NAMESPACES[namespace]
        await ctx.enable_components(tags={f"namespace:{canonical}"}, components={"tool"})
        return {
            "activated": canonical,
            "status": "ok",
            "deprecation_notice": (
                f"Namespace '{namespace}' has been consolidated into '{canonical}'. "
                f"Please use tools_activate(namespace='{canonical}') in future."
            ),
        }

    if namespace not in _LAZY_NAMESPACES:
        return {
            "error": (
                f"Unknown namespace {namespace!r}. "
                f"Choose from: {sorted(_LAZY_NAMESPACES)}"
            )
        }
    await ctx.enable_components(tags={f"namespace:{namespace}"}, components={"tool"})
    logger.info("Activated namespace '%s' for session.", namespace)
    return {"activated": namespace, "status": "ok"}





# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@mcp.prompt(name="sync_context", description="Project Sync: Re-orient and align your knowledge.")
def prompt_sync_context() -> str:
    return PROMPT_REGISTRY["sync_context"]


@mcp.prompt(name="plan_feature", description="Feature Architect: Decompose and design.")
def prompt_plan_feature() -> str:
    return PROMPT_REGISTRY["plan_feature"]


@mcp.prompt(name="run_audit", description="Quality Audit: Bugs and drift analysis.")
def prompt_run_audit() -> str:
    return PROMPT_REGISTRY["run_audit"]


@mcp.prompt(name="close_session", description="Session Wrap: Summarize and persist.")
def prompt_close_session() -> str:
    return PROMPT_REGISTRY["close_session"]


@mcp.prompt(name="sub_agent_spinup", description="Initialize a specialized sub-agent persona.")
def prompt_sub_agent_spinup(
    persona: Annotated[str, Field(description="Persona key: auditor | architect | triage | mapper")],
    task: Annotated[str, Field(description="The specific task the sub-agent should perform")],
) -> str:
    return get_sub_agent_instructions(persona, task)


# Globally hide all lazy namespaces — activated per-session via tools_activate
mcp.disable(tags={f"namespace:{ns}" for ns in _LAZY_NAMESPACES})


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


async def _health(request: Request) -> JSONResponse:  # noqa: ARG001
    """GET /health — returns 200 OK or 503 with degraded component identified."""
    status: dict[str, str] = {"db": "unknown", "ollama": "unknown"}
    http_status = 200

    try:
        conn = get_conn()
        conn.execute("MATCH (s:SchemaMeta) RETURN s LIMIT 1")
        status["db"] = "connected"
    except Exception as exc:  # noqa: BLE001
        status["db"] = f"error: {exc}"
        http_status = 503

    ollama_base = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.head(ollama_base)
            if resp.status_code < 500:
                status["ollama"] = "available"
            else:
                status["ollama"] = f"error: {resp.status_code}"
                http_status = 503
    except Exception as exc:  # noqa: BLE001
        status["ollama"] = f"error: {exc}"
        http_status = 503

    overall = "ok" if http_status == 200 else "degraded"
    return JSONResponse({"status": overall, **status}, status_code=http_status)


_TRANSPORT = os.getenv("MCP_TRANSPORT", "http")


def run() -> None:
    if _TRANSPORT == "stdio":
        mcp.run(transport="stdio")
    elif _TRANSPORT == "http":
        _run_http()
    else:
        mcp.run(
            transport=cast(
                Literal["stdio", "http", "sse", "streamable-http"], _TRANSPORT
            ),
            host=_HOST,
            port=_PORT,
        )


def _run_http() -> None:
    app_http = mcp.http_app(transport="streamable-http", path="/mcp")
    app_sse = mcp.http_app(transport="sse", path="/sse")

    @asynccontextmanager
    async def combined_lifespan(app_instance: Starlette) -> AsyncGenerator[None, None]:
        async with app_http.router.lifespan_context(app_instance):
            async with app_sse.router.lifespan_context(app_instance):
                yield

    health_route = Route("/health", _health, methods=["GET"])

    app = Starlette(
        routes=[health_route] + app_http.router.routes + app_sse.router.routes,
        lifespan=combined_lifespan,
    )

    if AUTH_ENABLED:
        app.add_middleware(ApiKeyMiddleware)  # type: ignore[arg-type]
        logger.info("API key authentication enabled.")

    async def serve() -> None:
        config = uvicorn.Config(
            app,
            host=_HOST,
            port=_PORT,
            lifespan="on",
            ws="websockets-sansio",
            log_level="warning",
        )
        logger.info(
            "Starting server %r (HTTP: /mcp, SSE: /sse, Health: /health) on %s:%s",
            mcp.name,
            _HOST,
            _PORT,
        )
        server = uvicorn.Server(config)
        await server.serve()

    anyio.run(serve)
