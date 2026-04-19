from __future__ import annotations

import json

import pytest
from starlette.requests import Request


def _request(path: str = "/", query: str = "") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": query.encode(),
            "headers": [],
        }
    )


def _json(response) -> dict:
    return json.loads(response.body.decode())


@pytest.mark.asyncio
async def test_get_server_info_matches_runtime_metadata():
    from mem_graph import __version__
    from mem_graph import server as server_mod

    payload = server_mod.get_server_info()

    assert payload == {
        "name": server_mod.SERVER_NAME,
        "version": __version__,
        "api_version": server_mod.SERVER_API_VERSION,
        "website": server_mod.SERVER_WEBSITE,
    }


@pytest.mark.asyncio
async def test_info_route_returns_server_metadata():
    from mem_graph import server as server_mod

    response = server_mod._info(_request("/info"))

    assert response.status_code == 200
    assert _json(response) == {
        "name": server_mod.SERVER_NAME,
        "version": server_mod.SERVER_VERSION,
        "api_version": server_mod.SERVER_API_VERSION,
        "website": server_mod.SERVER_WEBSITE,
    }


@pytest.mark.asyncio
async def test_dashboard_metadata_routes_return_catalogs():
    from mem_graph import server as server_mod

    force_graph = server_mod._force_graph_js(_request("/force-graph.js"))
    agents = server_mod._dashboard_agents(_request("/dashboard/api/agents"))
    workflows = server_mod._dashboard_workflows(
        _request("/dashboard/api/workflows")
    )
    tools = await server_mod._dashboard_tools(_request("/dashboard/api/tools"))

    assert force_graph.status_code == 200
    assert "ForceGraph" in force_graph.body.decode()
    assert agents.status_code == 200
    assert _json(agents)["count"] > 0
    assert workflows.status_code == 200
    workflow_payload = _json(workflows)
    assert {workflow["key"] for workflow in workflow_payload["workflows"]} >= {
        "autopilot_graph",
        "managed_workflow_graph",
        "package_audit",
    }
    assert "graph TD" in workflow_payload["workflows"][0]["mermaid"]
    assert tools.status_code == 200
    assert _json(tools)["count"] > 0
