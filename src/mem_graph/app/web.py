"""Starlette routes and dashboard API handlers."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from ..agents.discovery import discover_agent_modules, workflow_definitions
from ..db import db_get_connection
from ..tools import graph
from ..tools.filesystem import status as filesystem_status
from ..tools.filesystem import tree as filesystem_tree
from .constants import SERVER_STARTED_AT, STATIC_DIR
from .telemetry import dashboard_graph_telemetry, query_rows
from .tools import catalog_tools, get_namespace, server_info_payload

logger = logging.getLogger(__name__)
JS_MIME = "text/javascript"
CSS_MIME = "text/css"


def _info(request: Request) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(server_info_payload())


async def _health(request: Request) -> JSONResponse:  # noqa: ARG001
    status: dict[str, str] = {"db": "unknown", "ollama": "unknown"}
    http_status = 200

    try:
        conn = db_get_connection()
        conn.execute("MATCH (s:SchemaMeta) RETURN s LIMIT 1")
        status["db"] = "connected"
    except Exception as exc:  # noqa: BLE001
        status["db"] = f"error: {exc}"
        http_status = 503

    import os

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


def _static_page(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / name)


def _dashboard(request: Request) -> FileResponse:  # noqa: ARG001
    return _static_page("dashboard.html")


def _explore(request: Request) -> FileResponse:  # noqa: ARG001
    return _static_page("explore.html")


def _agents(request: Request) -> FileResponse:  # noqa: ARG001
    return _static_page("agents.html")


def _tools(request: Request) -> FileResponse:  # noqa: ARG001
    return _static_page("tools.html")


def _evals(request: Request) -> FileResponse:  # noqa: ARG001
    return _static_page("evals.html")


def _dashboard_js(_request: Request) -> FileResponse:  # noqa: ARG001
    return FileResponse(
        _asset_path("js/dashboard.js", "dashboard.js"), media_type=JS_MIME
    )


def _dashboard_css(_request: Request) -> FileResponse:  # noqa: ARG001
    return FileResponse(
        _asset_path("style/dashboard.css", "dashboard.css"), media_type=CSS_MIME
    )


def _force_graph_js(_request: Request) -> Response:  # noqa: ARG001
    path = _asset_path("js/force-graph.js", "force-graph.js")
    return Response(path.read_text(encoding="utf-8"), media_type=JS_MIME)


def _asset_path(current: str, legacy: str):
    current_path = STATIC_DIR / current
    if current_path.exists():
        return current_path
    return STATIC_DIR / legacy


def _dashboard_system(request: Request) -> JSONResponse:  # noqa: ARG001
    db_status = "connected"
    telemetry: dict[str, Any] = {}
    try:
        query_rows("MATCH (s:SchemaMeta) RETURN s LIMIT 1")
        telemetry = dashboard_graph_telemetry()
    except Exception as exc:  # noqa: BLE001
        db_status = f"error: {exc}"

    status = "ok" if db_status == "connected" else "degraded"
    return JSONResponse(
        {
            "server": server_info_payload(),
            "status": status,
            "uptime_seconds": round(time.monotonic() - SERVER_STARTED_AT, 3),
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


def dashboard_tools_handler(mcp: FastMCP):
    async def _dashboard_tools(request: Request) -> JSONResponse:  # noqa: ARG001
        tool_defs = await catalog_tools(mcp)
        groups: dict[str, list[dict[str, Any]]] = {}
        for tool_def in tool_defs:
            namespace = get_namespace(tool_def)
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

    return _dashboard_tools


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
    rows = query_rows(query, params)
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


async def _dashboard_projects(_request: Request) -> JSONResponse:  # noqa: ARG001
    try:
        from ..tools.work.projects import project_list

        result = await project_list()
        projects = result.get("projects", [])
        return JSONResponse([{"id": p["id"], "name": p["name"]} for p in projects])
    except Exception as exc:
        logger.error("Failed to load projects: %s", exc)
        return JSONResponse({"error": "Failed to load projects"}, status_code=500)


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
    try:
        details = await graph.graph_queries.get_node_details(
            request.path_params["node_id"]
        )
        if not isinstance(details, dict):
            return JSONResponse(details.model_dump())
        return JSONResponse(details, status_code=404 if "error" in details else 200)
    except Exception as exc:
        logger.error("Failed to load node details: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


async def _dashboard_search(request: Request) -> JSONResponse:
    try:
        node_types_raw = request.query_params.get("node_types")
        node_types = (
            [item for item in node_types_raw.split(",") if item]
            if node_types_raw
            else None
        )
        results = await graph.graph_queries.search_graph(
            query=request.query_params.get("query", ""),
            project_id=request.query_params.get("project_id"),
            node_types=node_types,
            limit=int(request.query_params.get("limit", 20)),
        )
        return JSONResponse([result.model_dump() for result in results])
    except Exception as exc:
        logger.error("Failed to search graph: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


def _dashboard_styles(request: Request) -> JSONResponse:  # noqa: ARG001
    return JSONResponse({"styles": graph.graph_queries.load_node_styles()})


def _file_tree(request: Request) -> FileResponse:  # noqa: ARG001
    return _static_page("file-tree.html")


def _query_flag(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


async def _file_tree_data(request: Request) -> JSONResponse:
    try:
        payload = await filesystem_tree.get_file_tree(
            root_path=request.query_params.get("root_path"),
            project_id=request.query_params.get("project_id"),
            include_hidden=_query_flag(
                request.query_params.get("include_hidden"), False
            ),
            include_graph_metadata=_query_flag(
                request.query_params.get("include_graph_metadata"),
                True,
            ),
            max_depth=int(request.query_params.get("max_depth", 8)),
        )
        if isinstance(payload, dict):
            status_code = 400 if "error" in payload else 200
            return JSONResponse(payload, status_code=status_code)
        return JSONResponse(payload.model_dump(), status_code=200)
    except Exception as exc:
        logger.error("File tree data error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


async def _file_tree_violations(request: Request) -> JSONResponse:
    payload = await filesystem_status.get_file_violations(
        file_path=request.query_params.get("file_path", ""),
        root_path=request.query_params.get("root_path"),
        project_id=request.query_params.get("project_id"),
        include_resolved=_query_flag(
            request.query_params.get("include_resolved"), True
        ),
    )
    if isinstance(payload, dict):
        status_code = 400 if "error" in payload else 200
        return JSONResponse(payload, status_code=status_code)
    return JSONResponse(payload.model_dump(), status_code=200)


def build_http_app(
    mcp: FastMCP,
    *,
    with_lifespan: bool = True,
) -> Starlette:
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
        # Both FastMCP transport apps share the same server instance and therefore
        # the same lifespan. Entering both would initialize the database twice and
        # trip Ladybug's single-writer file lock during startup.
        async with app_http.router.lifespan_context(app_instance):
            yield

    web_routes = [
        Route("/info", _info, methods=["GET"]),
        Route("/health", _health, methods=["GET"]),
        Route("/", _dashboard, methods=["GET"]),
        Route("/dashboard", _dashboard, methods=["GET"]),
        Route("/explore", _explore, methods=["GET"]),
        Route("/agents", _agents, methods=["GET"]),
        Route("/tools", _tools, methods=["GET"]),
        Route("/evals", _evals, methods=["GET"]),
        Route("/file-tree", _file_tree, methods=["GET"]),
        Route("/dashboard.js", _dashboard_js, methods=["GET"]),
        Route("/dashboard.css", _dashboard_css, methods=["GET"]),
        Route("/force-graph.js", _force_graph_js, methods=["GET"]),
        Mount("/js", StaticFiles(directory=STATIC_DIR / "js"), name="js"),
        Mount("/style", StaticFiles(directory=STATIC_DIR / "style"), name="style"),
        Route("/dashboard/api/system", _dashboard_system, methods=["GET"]),
        Route("/dashboard/api/agents", _dashboard_agents, methods=["GET"]),
        Route("/dashboard/api/workflows", _dashboard_workflows, methods=["GET"]),
        Route("/dashboard/api/tools", dashboard_tools_handler(mcp), methods=["GET"]),
        Route("/dashboard/api/evals", _dashboard_evals, methods=["GET"]),
        Route("/dashboard/api/projects", _dashboard_projects, methods=["GET"]),
        Route("/dashboard/api/graph", _dashboard_graph, methods=["GET"]),
        Route("/dashboard/api/node/{node_id}", _dashboard_node, methods=["GET"]),
        Route("/dashboard/api/search", _dashboard_search, methods=["GET"]),
        Route("/dashboard/api/styles", _dashboard_styles, methods=["GET"]),
        Route("/file-tree/api/tree", _file_tree_data, methods=["GET"]),
        Route("/file-tree/api/violations", _file_tree_violations, methods=["GET"]),
    ]

    return Starlette(
        routes=web_routes
        if app_http is None or app_sse is None
        else web_routes + app_http.router.routes + app_sse.router.routes,
        lifespan=combined_lifespan if with_lifespan else None,
    )
