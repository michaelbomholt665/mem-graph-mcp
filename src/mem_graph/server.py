#!/usr/bin/env python3
# ruff: noqa: E402
"""FastMCP server bootstrap for syntx-memory."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv

load_dotenv()

from .app.constants import SERVER_NAME, SERVER_VERSION
from .observability.logfire_setup import setup_logfire
from .observability.otel_setup import setup_observability

setup_logfire(service_name=SERVER_NAME, service_version=SERVER_VERSION)
setup_observability(service_name=SERVER_NAME, service_version=SERVER_VERSION)

if not os.getenv("OPENAI_API_KEY"):
    os.environ.setdefault("OPENAI_API_KEY", "missing-key-set-in-env-file")

import anyio
import uvicorn
from fastmcp import FastMCP
from fastmcp.server.context import Context
from fastmcp.server.providers.skills import (
    SkillsProvider,  # type: ignore[import-untyped]
)
from fastmcp.server.transforms import PromptsAsTools, ResourcesAsTools
from fastmcp.server.transforms.search import BM25SearchTransform
from mcp.types import Icon
from starlette.responses import JSONResponse

from .app import telemetry, web
from .app.auth import StaticTokenVerifier, build_auth_provider
from .app.constants import (
    HOST,
    LAZY_NAMESPACES,
    PORT,
    SERVER_API_VERSION,
    SERVER_WEBSITE,
    TRANSPORT,
)
from .app.lifespan import build_lifespan
from .app.middleware import LoggingMiddleware
from .app.prompts import register_prompts
from .app.resources import register_resources
from .app.tools import (
    get_namespace,
    get_server_info,
    register_tools,
    server_info_payload,
)
from .logging import logging_setup_engine
from .sandbox.provider import build_session_code_mode
from .services.sandbox_sessions import configure_sandbox_manager, sandbox_manager
from .tools import background, graph, integrations
from .tools.agents import audit, diagrams, orchestrator, triage
from .tools.agents import map as map_tool
from .tools.code import parser as code_parser
from .tools.filesystem import filesystem
from .tools.memory import conversation, memory, notes
from .tools.sandbox import session as sandbox_session
from .tools.work import decisions, projects, tasks, violations

# Force all standard logging to stderr
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(name)s - %(levelname)s - %(message)s",
)

logging_setup_engine(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_auth_provider = build_auth_provider()


def _lifespan(server: FastMCP):
    return build_lifespan(mcp)(server)


mcp = FastMCP(
    SERVER_NAME,
    instructions=(
        "Agent memory store for Syntx. "
        "Captures conversations, tasks, decisions, notes, violations "
        "and enables semantic recall across sessions.\n\n"
        "Start with system_inspect() for a full orientation, or search_tools(query='...') "
        "to find capabilities by natural language. "
        "Use list_task_types() to see public task categories for sub-agent dispatch, "
        "list_agents() for registered sub-agents, and tools_activate(namespace=...) "
        "to unlock lazy namespaces. "
        "Use list_resources() and list_prompts() to browse resource and prompt catalogs."
    ),
    lifespan=_lifespan,
    list_page_size=50,
    auth=_auth_provider,
    version=SERVER_VERSION,
    website_url=SERVER_WEBSITE,
    icons=[
        Icon(
            src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy5vcmcvMjAwMC9zdmciIHdpZHRoPSI0OCIgaGVpZ2h0PSI0OCIgdmlld0JveD0iMCAwIDQ4IDQ4Ij48cmVjdCBmaWxsPSIjRkZGIiBmaWxsLW9wYWNpdHk9Ii4wMSIgd2lkdGg9IjQ4IiBoZWlnaHQ9IjQ4Ii8+PHBhdGggZmlsbD0iIzEyNzZkMiIgZD0iTTI0IDRDMTIuOTUgNCA0IDE2Ljk1IDQgMjhzOC45NSAyNCAyMCAyNCAyMC04Ljk1IDIwLTIwUzM1LjA1IDQgMjQgNHptLTQgMzZINjYuODN2LTEyCzMwSDE2VjZ6Ii8+PC9zdmc+",
            mimeType="image/svg+xml",
        )
    ],
)
mcp.add_middleware(LoggingMiddleware())

if _auth_provider is not None:
    logger.info("API key authentication enabled (StaticTokenVerifier).")

for sub_mcp in (
    conversation.mcp,
    memory.mcp,
    projects.mcp,
    tasks.mcp,
    decisions.mcp,
    notes.mcp,
    violations.mcp,
    audit.mcp,
    diagrams.mcp,
    map_tool.mcp,
    orchestrator.mcp,
    triage.mcp,
    filesystem.mcp,
    background.mcp,
    graph.mcp,
    integrations.mcp,
    code_parser.mcp,
    sandbox_session.mcp,
):
    mcp.mount(sub_mcp)

mcp.add_provider(SkillsProvider("skills"))
register_tools(mcp)
register_resources(mcp)
register_prompts(mcp)
_sandbox_manager = configure_sandbox_manager(repo_root=Path.cwd())
if _sandbox_manager.enabled:
    mcp.add_transform(build_session_code_mode(sandbox_manager()))
mcp.add_transform(ResourcesAsTools(mcp))
mcp.add_transform(PromptsAsTools(mcp))
mcp.add_transform(
    BM25SearchTransform(
        max_results=8,
        always_visible=["system_inspect", "list_agents", "list_task_types"],
    )
)
mcp.disable(tags={f"namespace:{namespace}" for namespace in LAZY_NAMESPACES})


@mcp.tool()
async def _dashboard_api_projects(ctx: Context) -> JSONResponse:  # noqa: ARG001
    return await _dashboard_projects(None)  # type: ignore[arg-type]


def build_http_app(*, with_lifespan: bool = True):
    return web.build_http_app(mcp, with_lifespan=with_lifespan)


def run() -> None:
    if TRANSPORT == "stdio":
        mcp.run(transport="stdio", show_banner=False)
    elif TRANSPORT in ("http", "mcp", "streamable-http"):
        _run_http()
    else:
        mcp.run(
            transport=cast(
                Literal["stdio", "http", "sse", "streamable-http"], TRANSPORT
            ),
            host=HOST,
            port=PORT,
            show_banner=False,
        )


def _run_http() -> None:
    app = build_http_app()

    async def serve() -> None:
        config = uvicorn.Config(
            app,
            host=HOST,
            port=PORT,
            lifespan="on",
            ws="websockets-sansio",
            log_level="warning",
        )
        # Logs moved to lifespan for better positioning (below logo)
        server = uvicorn.Server(config)
        await server.serve()

    anyio.run(serve)


_dashboard_graph_telemetry = telemetry.dashboard_graph_telemetry
_query_rows = telemetry.query_rows
_safe_count = telemetry.safe_count
_get_namespace = get_namespace
_server_info_payload = server_info_payload

_agents = web._agents
_dashboard = web._dashboard
_dashboard_agents = web._dashboard_agents
_dashboard_css = web._dashboard_css
_dashboard_evals = web._dashboard_evals
_dashboard_graph = web._dashboard_graph
_dashboard_js = web._dashboard_js
_dashboard_node = web._dashboard_node
_dashboard_projects = web._dashboard_projects
_dashboard_search = web._dashboard_search
_dashboard_styles = web._dashboard_styles
_dashboard_system = web._dashboard_system
_dashboard_tools = web.dashboard_tools_handler(mcp)
_dashboard_workflows = web._dashboard_workflows
_evals = web._evals
_explore = web._explore
_file_tree = web._file_tree
_file_tree_data = web._file_tree_data
_file_tree_violations = web._file_tree_violations
_force_graph_js = web._force_graph_js
_health = web._health
_info = web._info
_jsonable_tool_schema = web._jsonable_tool_schema
_query_flag = web._query_flag
_tools = web._tools

__all__ = [
    "SERVER_NAME",
    "SERVER_VERSION",
    "SERVER_API_VERSION",
    "SERVER_WEBSITE",
    "StaticTokenVerifier",
    "build_http_app",
    "get_server_info",
    "mcp",
    "run",
]


if __name__ == "__main__":
    run()
