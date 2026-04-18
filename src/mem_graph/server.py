#!/usr/bin/env python3
# src/mem_graph/server.py
# ruff: noqa: E402
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
        integrations — jina_fetch_issues, jina_find_code_for_ticket, jina_find_tickets_for_file

FastMCP 3.0 Upgrades
---------------------
- Dependency Injection: ``Depends(db_get_connection)`` injects the DB connection.
- Auth: ``StaticTokenVerifier`` replaces the custom ``auth_api_middleware``.
- Middleware: ``LoggingMiddleware`` provides MCP-level structured logging.
- Pagination: ``list_page_size=50`` prevents context window overflow.
- Resources: URI templates for memory, work, and audit entities.
- Context: ``ctx.report_progress()``, ``ctx.info()``, ``ctx.sample()`` in tools.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, AsyncGenerator, Literal, cast

from dotenv import load_dotenv

load_dotenv()

from . import __version__
from .observability.logfire_setup import setup_logfire, shutdown_logfire
from .observability.otel_setup import setup_observability, shutdown_observability

SERVER_NAME = "syntx-memory"
SERVER_VERSION = __version__

# Initialize observability before importing FastMCP, MCP, Pydantic AI agents, or
# any tool modules that may create module-level agent instances.
setup_logfire(service_name=SERVER_NAME, service_version=SERVER_VERSION)
setup_observability(service_name=SERVER_NAME, service_version=SERVER_VERSION)

# Pre-emptively set a dummy key to avoid pydantic-ai import-time crashes if no key is in .env.
if not os.getenv("OPENAI_API_KEY"):
    os.environ.setdefault("OPENAI_API_KEY", "missing-key-set-in-env-file")

import anyio
import httpx
import uvicorn
from anyio import to_thread
from fastmcp import FastMCP
from fastmcp.experimental.transforms.code_mode import (
    CodeMode,  # type: ignore[import-untyped]
)
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.context import Context
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.providers.skills import (
    SkillsProvider,  # type: ignore[import-untyped]
)
from mcp.types import Icon
from pydantic import Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from .agents.discovery import discover_agent_modules, workflow_definitions
from .db import db_close_engine, db_get_connection, db_init_engine
from .logging import logging_setup_engine

from .providers.openapi import build_openapi_provider
from .resources.prompts import PROMPT_REGISTRY, get_sub_agent_instructions
from .services.summarizer import start_worker, stop_worker
from .services.task_queue import task_queue
from .tools import background, graph, integrations
from .tools.agents import audit, diagrams, orchestrator, triage
from .tools.agents import map as map_tool
from .tools.filesystem import filesystem
from .tools.filesystem import status as filesystem_status
from .tools.filesystem import tree as filesystem_tree
from .tools.memory import conversation, memory, notes
from .tools.work import decisions, projects, tasks, violations

logging_setup_engine(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_HOST = os.getenv("MCP_HOST", "127.0.0.1")
_PORT = int(os.getenv("MCP_PORT", "9100"))
_BASE_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _BASE_DIR / "static"
SERVER_API_VERSION = "1.0"
SERVER_WEBSITE = os.getenv(
    "MEM_GRAPH_WEBSITE", "https://github.com/michael/syntx-memory"
)
_SERVER_STARTED_AT = time.monotonic()

# Consolidated namespaces
_LAZY_NAMESPACES: frozenset[str] = frozenset(
    {
        "memory",
        "work",
        "notes",
        "audit",
        "filesystem",
        "background",
        "graph",
        "integrations",
    }
)

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
    s.strip() for s in os.getenv("MEM_GRAPH_OPENAPI_SPECS", "").split(",") if s.strip()
]

# ---------------------------------------------------------------------------
# Auth: StaticTokenVerifier (replaces custom auth_api_middleware)
# ---------------------------------------------------------------------------

_RAW_KEYS = os.getenv("MEM_GRAPH_API_KEYS", "").strip()
_ALLOWED_KEYS: frozenset[str] = (
    frozenset(k.strip() for k in _RAW_KEYS.split(",") if k.strip())
    if _RAW_KEYS
    else frozenset()
)


class StaticTokenVerifier(TokenVerifier):
    """
    FastMCP 3.0 auth provider that validates a static set of Bearer tokens.

    Replaces the legacy ``auth_api_middleware``. When ``MEM_GRAPH_API_KEYS`` is
    set the verifier is wired into the ``FastMCP`` constructor as ``auth=``.
    Each key grants both ``memory:read`` and ``memory:write`` scopes.
    """

    def __init__(self, keys: frozenset[str]) -> None:
        super().__init__(required_scopes=["memory:read", "memory:write"])
        self._keys = keys

    async def verify_token(self, token: str) -> AccessToken | None:
        if token in self._keys:
            return AccessToken(
                token=token,
                client_id="local",
                scopes=["memory:read", "memory:write"],
            )
        return None


_auth_provider: StaticTokenVerifier | None = (
    StaticTokenVerifier(_ALLOWED_KEYS) if _ALLOWED_KEYS else None
)

# ---------------------------------------------------------------------------
# MCP-level Middleware: structured logging for every tool call
# ---------------------------------------------------------------------------


class LoggingMiddleware(Middleware):
    """
    FastMCP 3.0 middleware: logs every tool call with elapsed time.

    Captures ``tools/call`` requests and adds structured log lines at
    INFO level so each AI action leaves a clear audit trail.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        import time

        tool_name: str = getattr(context.message, "name", "<unknown>")
        start = time.monotonic()
        try:
            result = await call_next(context)
            elapsed = (time.monotonic() - start) * 1000
            logger.info("tool_call tool=%s elapsed_ms=%.1f", tool_name, elapsed)
            return result
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(
                "tool_error tool=%s elapsed_ms=%.1f error=%s",
                tool_name,
                elapsed,
                exc,
            )
            raise


_BANNER = r"""
__  __ ______ __  __      _____  _____            _____  _    _
  |  \/  |  ____|  \/  |    / ____|  __ \     /\    |  __ \| |  | |
  | \  / | |__  | \  / |   | |  __| |__) |   /  \   | |__) | |__| |
  | |\/| |  __| | |\/| |   | | |_ |  _  /   / /\ \  |  ___/|  __  |
  | |  | | |____| |  | |   | |__| | | \ \  / ____ \ | |    | |  | |
  |_|  |_|______|_|  |_|    \_____|_|  \_\/_/    \_\|_|    |_|  |_|

  __  __  _____ _____
 |  \/  |/ ____|  __ \
 | \  / | |    | |__) |
 | |\/| | |    |  ___/
 | |  | | |____| |
 |_|  |_|\_____|_|
"""


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncGenerator[None, None]:  # noqa: ARG001
    if sys.stderr.isatty():
        print(_BANNER, file=sys.stderr)
        print(
            f"  Version: {SERVER_VERSION} | CodeMode: ENABLED | Host: {_HOST}:{_PORT}\n",
            file=sys.stderr,
        )

    await to_thread.run_sync(db_init_engine)
    start_worker()
    await task_queue.startup()
    await _load_openapi_providers()
    logger.info("mem-graph server ready.")
    yield
    pending = await task_queue.shutdown()
    if pending["queued_cancelled"] or pending["running_cancelled"]:
        logger.warning(
            "background task queue cleared on shutdown queued=%s running=%s",
            pending["queued_cancelled"],
            pending["running_cancelled"],
        )
    await stop_worker()
    await to_thread.run_sync(db_close_engine)
    shutdown_observability()
    shutdown_logfire()
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


def _server_info_payload() -> dict[str, str]:
    return {
        "name": SERVER_NAME,
        "version": SERVER_VERSION,
        "api_version": SERVER_API_VERSION,
        "website": SERVER_WEBSITE,
    }


mcp = FastMCP(
    SERVER_NAME,
    instructions=(
        "Agent memory store for Syntx. "
        "Captures conversations, tasks, decisions, notes, violations "
        "and enables semantic recall across sessions.\n\n"
        "TOOL DISCOVERY: Only core tools are visible at startup. "
        "Call tools_activate(namespace=<name>) to unlock a group of "
        "specialised tools for your current session. "
        "Available namespaces: memory, work, notes, audit, filesystem, background, graph, integrations.\n"
        "Call tools_search(query='...') if you're unsure which namespace to use."
    ),
    lifespan=lifespan,
    transforms=[CodeMode()],
    list_page_size=50,
    auth=_auth_provider,
    version=SERVER_VERSION,
    website_url=SERVER_WEBSITE,
    icons=[
        Icon(
            src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0OCIgaGVpZ2h0PSI0OCIgdmlld0JveD0iMCAwIDQ4IDQ4Ij48cmVjdCBmaWxsPSIjRkZGIiBmaWxsLW9wYWNpdHk9Ii4wMSIgd2lkdGg9IjQ4IiBo ZWlnaHQ9IjQ4Ii8+PHBhdGggZmlsbD0iIzEyNzZkMiIgZD0iTTI0IDRDMTIuOTUgNCA0IDE2Ljk1IDQgMjhzOC45NSAyNCAyMCAyNCAyMC04Ljk1IDIwLTIwUzM1LjA1IDQgMjQgNHptLTQgMzZINjYuODN2LTEyCzMwSDE2VjZ6Ii8+PC9zdmc+",
            mimeType="image/svg+xml",
        )
    ],
)

# Register MCP-level middleware for structured logging
mcp.add_middleware(LoggingMiddleware())

if _auth_provider is not None:
    logger.info("API key authentication enabled (StaticTokenVerifier).")

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
mcp.mount(background.mcp)
mcp.mount(graph.mcp)
mcp.mount(integrations.mcp)

# Skills directory provider — drop .py files into skills/ to add tools on restart
mcp.add_provider(SkillsProvider("skills"))

# (OpenAPI providers are loaded asynchronously in lifespan → _load_openapi_providers)


@mcp.tool()
async def get_server_info() -> dict[str, str]:
    """Return stable server metadata for clients and operators."""
    return _server_info_payload()


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

    all_tools = await mcp.list_tools()

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
                "One of: memory, work, notes, audit, filesystem, background, graph, integrations."
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
    audit      — audit_package, map_codebase, triage_violations, decision_review,
                 orchestrate_codebase, autopilot_remediate
    filesystem — file_read, file_write, file_edit, file_delete, file_search, file_grep
    background — get_task_status, cancel_task
    graph      — get_graph_snapshot, get_node_details, search_graph
    integrations — jina_fetch_issues, jina_find_code_for_ticket, jina_find_tickets_for_file
    """
    # Handle deprecated namespace aliases
    if namespace in _DEPRECATED_NAMESPACES:
        canonical = _DEPRECATED_NAMESPACES[namespace]
        await ctx.enable_components(
            tags={f"namespace:{canonical}"}, components={"tool"}
        )
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
    await ctx.info(f"Activated namespace '{namespace}' for session.")
    logger.info("Activated namespace '%s' for session.", namespace)
    return {"activated": namespace, "status": "ok"}


# ---------------------------------------------------------------------------
# MCP Resource Templates (Phase 2)
# ---------------------------------------------------------------------------


@mcp.resource(
    "memory://{memory_id}",
    description="Read a stored memory node by its ID.",
    mime_type="application/json",
)
async def resource_memory(memory_id: str) -> str:
    """Retrieve a single Memory node as JSON."""
    conn = db_get_connection()
    result = conn.execute(
        """
        MATCH (m:Memory {id: $id})
        OPTIONAL MATCH (m)<-[:PROJECT_MEMORY]-(p:Project)
        RETURN m.id, m.kind, m.scope, m.content, m.confidence,
               m.created_at, m.updated_at, m.expires_at, p.name AS project
        """,
        {"id": memory_id},
    )
    if isinstance(result, list):
        result = result[0]
    rows = cast(list[list[Any]], result.get_all())
    if not rows:
        return json.dumps({"error": f"Memory {memory_id!r} not found"})
    r = rows[0]
    return json.dumps(
        {
            "id": r[0],
            "kind": r[1],
            "scope": r[2],
            "content": r[3],
            "confidence": r[4],
            "created_at": str(r[5]),
            "updated_at": str(r[6]),
            "expires_at": str(r[7]) if r[7] else None,
            "project": r[8],
        }
    )


@mcp.resource(
    "memory://list",
    description="List the 50 most recently created active memories.",
    mime_type="application/json",
)
async def resource_memory_list() -> str:
    """Return a JSON list of the most recent active memories."""
    conn = db_get_connection()
    result = conn.execute(
        """
        MATCH (m:Memory)
        WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
        RETURN m.id, m.kind, m.scope, m.content, m.confidence, m.created_at
        ORDER BY m.created_at DESC
        LIMIT 50
        """
    )
    if isinstance(result, list):
        result = result[0]
    memories = [
        {
            "id": r[0],
            "kind": r[1],
            "scope": r[2],
            "content": r[3],
            "confidence": r[4],
            "created_at": str(r[5]),
        }
        for r in cast(list[list[Any]], result.get_all())
    ]
    return json.dumps({"memories": memories, "count": len(memories)})


@mcp.resource(
    "work://tasks/{task_id}",
    description="Read a work task node by its ID.",
    mime_type="application/json",
)
async def resource_task(task_id: str) -> str:
    """Retrieve a single Task node with linked decisions, violations, and blockers."""
    conn = db_get_connection()
    result = conn.execute(
        """
        MATCH (t:Task {id: $id})
        RETURN t.id, t.title, t.description, t.status, t.priority,
               t.phase, t.created_at, t.updated_at, t.completed_at
        """,
        {"id": task_id},
    )
    if isinstance(result, list):
        result = result[0]
    rows = cast(list[list[Any]], result.get_all())
    if not rows:
        return json.dumps({"error": f"Task {task_id!r} not found"})
    r = rows[0]
    return json.dumps(
        {
            "id": r[0],
            "title": r[1],
            "description": r[2],
            "status": r[3],
            "priority": r[4],
            "phase": r[5],
            "created_at": str(r[6]),
            "updated_at": str(r[7]),
            "completed_at": str(r[8]) if r[8] else None,
        }
    )


@mcp.resource(
    "work://projects/{project_id}",
    description="Read a project node, its tasks, and open violations by project ID.",
    mime_type="application/json",
)
async def resource_project(project_id: str) -> str:
    """Retrieve a Project node with task and violation counts."""
    conn = db_get_connection()
    result = conn.execute(
        """
        MATCH (p:Project {id: $id})
        RETURN p.id, p.name, p.description, p.status, p.repo_path, p.created_at
        """,
        {"id": project_id},
    )
    if isinstance(result, list):
        result = result[0]
    rows = cast(list[list[Any]], result.get_all())
    if not rows:
        return json.dumps({"error": f"Project {project_id!r} not found"})
    r = rows[0]

    # Count tasks and open violations
    task_result = conn.execute(
        "MATCH (p:Project {id: $id})-[:HAS_TASK]->(t) RETURN count(t)",
        {"id": project_id},
    )
    if isinstance(task_result, list):
        task_result = task_result[0]
    task_rows = cast(list[list[Any]], task_result.get_all())
    task_count: int = int(task_rows[0][0]) if task_rows else 0

    viol_result = conn.execute(
        "MATCH (p:Project {id: $id})-[:HAS_VIOLATION]->(v) WHERE v.status = 'open' RETURN count(v)",
        {"id": project_id},
    )
    if isinstance(viol_result, list):
        viol_result = viol_result[0]
    viol_rows = cast(list[list[Any]], viol_result.get_all())
    viol_count: int = int(viol_rows[0][0]) if viol_rows else 0

    return json.dumps(
        {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "status": r[3],
            "repo_path": r[4],
            "created_at": str(r[5]),
            "task_count": task_count,
            "open_violation_count": viol_count,
        }
    )


@mcp.resource(
    "audit://violations/{violation_id}",
    description="Read a code violation node by its ID.",
    mime_type="application/json",
)
async def resource_violation(violation_id: str) -> str:
    """Retrieve a single Violation node as JSON."""
    conn = db_get_connection()
    result = conn.execute(
        """
        MATCH (v:Violation {id: $id})
        OPTIONAL MATCH (p:Project)-[:HAS_VIOLATION]->(v)
        RETURN v.id, v.audit_id, v.rule, v.severity, v.status,
               v.file_path, v.description, v.detected_at, v.resolved_at, p.id AS project_id
        """,
        {"id": violation_id},
    )
    if isinstance(result, list):
        result = result[0]
    rows = cast(list[list[Any]], result.get_all())
    if not rows:
        return json.dumps({"error": f"Violation {violation_id!r} not found"})
    r = rows[0]
    return json.dumps(
        {
            "id": r[0],
            "audit_id": r[1],
            "rule": r[2],
            "severity": r[3],
            "status": r[4],
            "file_path": r[5],
            "description": r[6],
            "detected_at": str(r[7]),
            "resolved_at": str(r[8]) if r[8] else None,
            "project_id": r[9],
        }
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


@mcp.prompt(
    name="sync_context", description="Project Sync: Re-orient and align your knowledge."
)
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


@mcp.prompt(
    name="sub_agent_spinup", description="Initialize a specialized sub-agent persona."
)
def prompt_sub_agent_spinup(
    persona: Annotated[
        str, Field(description="Persona key: auditor | architect | triage | mapper")
    ],
    task: Annotated[
        str, Field(description="The specific task the sub-agent should perform")
    ],
) -> str:
    return get_sub_agent_instructions(persona, task)


# Globally hide all lazy namespaces — activated per-session via tools_activate
mcp.disable(tags={f"namespace:{ns}" for ns in _LAZY_NAMESPACES})


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


def _info(request: Request) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(_server_info_payload())


async def _health(request: Request) -> JSONResponse:  # noqa: ARG001
    """GET /health — returns 200 OK or 503 with degraded component identified."""
    status: dict[str, str] = {"db": "unknown", "ollama": "unknown"}
    http_status = 200

    try:
        conn = db_get_connection()
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


def _dashboard(request: Request) -> FileResponse:  # noqa: ARG001
    return FileResponse(_STATIC_DIR / "dashboard.html")


JS_MIME = "text/javascript"

CSS_MIME = "text/css"


def _dashboard_js(request: Request) -> FileResponse:  # noqa: ARG001
    return FileResponse(_STATIC_DIR / "dashboard.js", media_type=JS_MIME)


def _dashboard_css(request: Request) -> FileResponse:  # noqa: ARG001
    return FileResponse(_STATIC_DIR / "dashboard.css", media_type=CSS_MIME)



def _force_graph_js(request: Request) -> Response:  # noqa: ARG001
    return Response(
        (_STATIC_DIR / "force-graph.js").read_text(encoding="utf-8"),
        media_type=JS_MIME,
    )



def _query_rows(query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    conn = db_get_connection()
    result = conn.execute(query, params or {})
    if isinstance(result, list):
        result = result[0]
    return cast(list[list[Any]], result.get_all())


def _safe_count(query: str, params: dict[str, Any] | None = None) -> int:
    try:
        rows = _query_rows(query, params)
    except Exception:  # noqa: BLE001
        return 0
    return int(rows[0][0]) if rows else 0


def _dashboard_graph_telemetry() -> dict[str, Any]:
    node_labels = [
        "Agent",
        "Project",
        "Backend",
        "Task",
        "Decision",
        "Note",
        "Violation",
        "Memory",
        "Message",
        "CodeFile",
        "CodeSymbol",
        "JinaIssue",
        "EvalRun",
    ]
    relationship_names = [
        "HAS_BACKEND",
        "HAS_TASK",
        "HAS_DECISION",
        "HAS_NOTE",
        "HAS_VIOLATION",
        "HAS_FILE",
        "HAS_JINA_ISSUE",
        "HAS_EVAL_RUN",
        "PROJECT_MEMORY",
        "BACKEND_TASK",
        "BACKEND_DECISION",
        "BACKEND_SYMBOL",
        "BACKEND_VIOLATION",
        "TASK_BLOCKS",
        "TASK_SPAWNS",
        "TASK_DECISION",
        "TASK_VIOLATION",
        "TASK_NOTE",
        "DECISION_NOTE",
        "SUPERSEDES",
        "VIOLATION_RECURS",
        "SYMBOL_TASK",
        "SYMBOL_VIOLATION",
        "SYMBOL_DECISION",
        "AUTHORED_BY",
    ]
    node_counts = {
        label: _safe_count(f"MATCH (n:{label}) RETURN count(n)") for label in node_labels
    }
    edge_counts = {
        rel: _safe_count(f"MATCH ()-[r:{rel}]->() RETURN count(r)")
        for rel in relationship_names
    }
    task_status = {
        str(row[0] or "unknown"): int(row[1])
        for row in _query_rows(
            "MATCH (t:Task) RETURN t.status, count(t) ORDER BY t.status"
        )
    }
    violation_severity = {
        str(row[0] or "unknown"): int(row[1])
        for row in _query_rows(
            "MATCH (v:Violation) RETURN v.severity, count(v) ORDER BY v.severity"
        )
    }
    return {
        "node_count": sum(node_counts.values()),
        "edge_count": sum(edge_counts.values()),
        "node_counts": node_counts,
        "edge_counts": edge_counts,
        "task_status": task_status,
        "violation_severity": violation_severity,
    }


def _dashboard_system(request: Request) -> JSONResponse:  # noqa: ARG001
    db_status = "connected"
    telemetry: dict[str, Any] = {}
    try:
        _query_rows("MATCH (s:SchemaMeta) RETURN s LIMIT 1")
        telemetry = _dashboard_graph_telemetry()
    except Exception as exc:  # noqa: BLE001
        db_status = f"error: {exc}"

    status = "ok" if db_status == "connected" else "degraded"
    return JSONResponse(
        {
            "server": _server_info_payload(),
            "status": status,
            "uptime_seconds": round(time.monotonic() - _SERVER_STARTED_AT, 3),
            "db": {"status": db_status},
            "telemetry": telemetry,
        },
        status_code=200 if status == "ok" else 503,
    )



def _dashboard_agents(request: Request) -> JSONResponse:  # noqa: ARG001
    agents = discover_agent_modules()
    return JSONResponse({"agents": agents, "count": len(agents)})



def _dashboard_workflows(request: Request) -> JSONResponse:  # noqa: ARG001
    workflows = workflow_definitions()
    return JSONResponse({"workflows": workflows, "count": len(workflows)})



def _jsonable_tool_schema(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return str(value)


async def _dashboard_tools(request: Request) -> JSONResponse:  # noqa: ARG001
    tool_defs: list[Any] = []
    for provider in mcp.providers:
        if provider.__class__.__name__ == "SkillsDirectoryProvider":
            continue
        try:
            tool_defs.extend(await provider.list_tools())
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "dashboard_tool_provider_failed provider=%s error=%s",
                provider,
                exc,
            )
    groups: dict[str, list[dict[str, Any]]] = {}
    for tool_def in tool_defs:
        namespace = _get_namespace(tool_def)
        tags = list(getattr(tool_def, "tags", []) or [])
        input_schema = (
            getattr(tool_def, "inputSchema", None)
            or getattr(tool_def, "parameters", None)
            or getattr(tool_def, "input_schema", None)
        )
        groups.setdefault(namespace, []).append(
            {
                "name": tool_def.name,
                "description": tool_def.description or "",
                "namespace": namespace,
                "tags": tags,
                "input_schema": _jsonable_tool_schema(input_schema),
            }
        )
    for tools in groups.values():
        tools.sort(key=lambda item: item["name"])
    return JSONResponse(
        {
            "namespaces": [
                {"namespace": key, "tools": value, "count": len(value)}
                for key, value in sorted(groups.items())
            ],
            "count": sum(len(value) for value in groups.values()),
        }
    )


def _dashboard_evals(request: Request) -> JSONResponse:
    project_id = request.query_params.get("project_id")
    limit = min(max(int(request.query_params.get("limit", 20)), 1), 100)
    if project_id:
        query = f"""
            MATCH (p:Project {{id: $project_id}})-[:HAS_EVAL_RUN]->(e:EvalRun)
            RETURN e.id, e.mode, e.label, e.trigger, e.total_suites, e.passed_suites,
                   e.suite_pass_rate, e.total_duration_ms, e.report_path, e.summary,
                   e.started_at, e.completed_at, e.persisted_at, e.logfire_run_id, p.id
            ORDER BY e.started_at DESC, e.persisted_at DESC
            LIMIT {limit}
        """
        params: dict[str, Any] = {"project_id": project_id}
    else:
        query = f"""
            MATCH (e:EvalRun)
            OPTIONAL MATCH (p:Project)-[:HAS_EVAL_RUN]->(e)
            RETURN e.id, e.mode, e.label, e.trigger, e.total_suites, e.passed_suites,
                   e.suite_pass_rate, e.total_duration_ms, e.report_path, e.summary,
                   e.started_at, e.completed_at, e.persisted_at, e.logfire_run_id, p.id
            ORDER BY e.started_at DESC, e.persisted_at DESC
            LIMIT {limit}
        """
        params = {}
    rows = _query_rows(query, params)
    return JSONResponse(
        {
            "evals": [
                {
                    "id": row[0],
                    "mode": row[1],
                    "label": row[2],
                    "trigger": row[3],
                    "total_suites": row[4],
                    "passed_suites": row[5],
                    "suite_pass_rate": row[6],
                    "total_duration_ms": row[7],
                    "report_path": row[8],
                    "summary": row[9],
                    "started_at": str(row[10]) if row[10] else None,
                    "completed_at": str(row[11]) if row[11] else None,
                    "persisted_at": str(row[12]) if row[12] else None,
                    "logfire_run_id": row[13],
                    "project_id": row[14],
                }
                for row in rows

            ],
            "count": len(rows),
        }
    )



async def _dashboard_graph(request: Request) -> JSONResponse:
    node_types_raw = request.query_params.get("node_types")
    node_types = (
        [item for item in node_types_raw.split(",") if item] if node_types_raw else None
    )
    snapshot = await graph.graph_queries.get_graph_snapshot(
        project_id=request.query_params.get("project_id"),
        node_types=node_types,
        depth=int(request.query_params.get("depth", 2)),
        max_nodes=int(request.query_params.get("max_nodes", 240)),
    )
    return JSONResponse(snapshot.model_dump())


async def _dashboard_node(request: Request) -> JSONResponse:
    details = await graph.graph_queries.get_node_details(request.path_params["node_id"])
    if not isinstance(details, dict):
        return JSONResponse(details.model_dump())
    return JSONResponse(details, status_code=404 if "error" in details else 200)


async def _dashboard_search(request: Request) -> JSONResponse:
    node_types_raw = request.query_params.get("node_types")
    node_types = (
        [item for item in node_types_raw.split(",") if item] if node_types_raw else None
    )
    results = await graph.graph_queries.search_graph(
        query=request.query_params.get("query", ""),
        project_id=request.query_params.get("project_id"),
        node_types=node_types,
        limit=int(request.query_params.get("limit", 20)),
    )
    return JSONResponse([result.model_dump() for result in results])


def _dashboard_styles(request: Request) -> JSONResponse:  # noqa: ARG001
    return JSONResponse({"styles": graph.graph_queries.load_node_styles()})


def _file_tree(request: Request) -> FileResponse:  # noqa: ARG001
    return FileResponse(_STATIC_DIR / "file-tree.html")


def _file_tree_js(request: Request) -> FileResponse:  # noqa: ARG001
    return FileResponse(_STATIC_DIR / "file-tree.js", media_type=JS_MIME)



def _file_tree_css(request: Request) -> FileResponse:  # noqa: ARG001
    return FileResponse(_STATIC_DIR / "file-tree.css", media_type="text/css")


def _query_flag(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


async def _file_tree_data(request: Request) -> JSONResponse:
    payload = await filesystem_tree.get_file_tree(
        root_path=request.query_params.get("root_path"),
        project_id=request.query_params.get("project_id"),
        include_hidden=_query_flag(request.query_params.get("include_hidden"), False),
        include_graph_metadata=_query_flag(
            request.query_params.get("include_graph_metadata"),
            True,
        ),
        max_depth=int(request.query_params.get("max_depth", 8)),
    )
    status_code = 400 if isinstance(payload, dict) and "error" in payload else 200
    if hasattr(payload, "model_dump"):
        return JSONResponse(payload.model_dump(), status_code=status_code)
    return JSONResponse(payload, status_code=status_code)


async def _file_tree_violations(request: Request) -> JSONResponse:
    payload = await filesystem_status.get_file_violations(
        file_path=request.query_params.get("file_path", ""),
        root_path=request.query_params.get("root_path"),
        project_id=request.query_params.get("project_id"),
        include_resolved=_query_flag(
            request.query_params.get("include_resolved"), True
        ),
    )
    status_code = 400 if isinstance(payload, dict) and "error" in payload else 200
    if hasattr(payload, "model_dump"):
        return JSONResponse(payload.model_dump(), status_code=status_code)
    return JSONResponse(payload, status_code=status_code)


_TRANSPORT = os.getenv("MCP_TRANSPORT", "http").lower()


def run() -> None:
    if _TRANSPORT == "stdio":
        mcp.run(transport="stdio")
    elif _TRANSPORT in ("http", "mcp", "streamable-http"):
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
    app = build_http_app()

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
            "Starting server %r v%s (HTTP: /mcp, SSE: /sse, Info: /info, Health: /health, Dashboard: /dashboard, Files: /file-tree) on %s:%s",
            mcp.name,
            SERVER_VERSION,
            _HOST,
            _PORT,
        )
        server = uvicorn.Server(config)
        await server.serve()

    anyio.run(serve)


def build_http_app(*, with_lifespan: bool = True) -> Starlette:
    app_http = (
        mcp.http_app(transport="streamable-http", path="/mcp")
        if with_lifespan
        else None
    )
    app_sse = mcp.http_app(transport="sse", path="/sse") if with_lifespan else None

    @asynccontextmanager
    async def combined_lifespan(app_instance: Starlette) -> AsyncGenerator[None, None]:
        if app_http is None or app_sse is None:
            yield
            return
        async with app_http.router.lifespan_context(app_instance):
            async with app_sse.router.lifespan_context(app_instance):
                yield

    web_routes = [
        Route("/info", _info, methods=["GET"]),
        Route("/health", _health, methods=["GET"]),
        Route("/dashboard", _dashboard, methods=["GET"]),
        Route("/dashboard.js", _dashboard_js, methods=["GET"]),
        Route("/dashboard.css", _dashboard_css, methods=["GET"]),
        Route("/force-graph.js", _force_graph_js, methods=["GET"]),
        Route("/dashboard/api/system", _dashboard_system, methods=["GET"]),
        Route("/dashboard/api/agents", _dashboard_agents, methods=["GET"]),
        Route("/dashboard/api/workflows", _dashboard_workflows, methods=["GET"]),
        Route("/dashboard/api/tools", _dashboard_tools, methods=["GET"]),
        Route("/dashboard/api/evals", _dashboard_evals, methods=["GET"]),
        Route("/dashboard/api/graph", _dashboard_graph, methods=["GET"]),
        Route("/dashboard/api/node/{node_id}", _dashboard_node, methods=["GET"]),
        Route("/dashboard/api/search", _dashboard_search, methods=["GET"]),
        Route("/dashboard/api/styles", _dashboard_styles, methods=["GET"]),
        Route("/file-tree", _file_tree, methods=["GET"]),
        Route("/file-tree.js", _file_tree_js, methods=["GET"]),
        Route("/file-tree.css", _file_tree_css, methods=["GET"]),
        Route("/file-tree/api/tree", _file_tree_data, methods=["GET"]),
        Route("/file-tree/api/violations", _file_tree_violations, methods=["GET"]),
    ]

    return Starlette(
        routes=web_routes
        if app_http is None or app_sse is None
        else web_routes + app_http.router.routes + app_sse.router.routes,
        lifespan=combined_lifespan if with_lifespan else None,
    )
