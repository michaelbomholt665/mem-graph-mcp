from __future__ import annotations

import json
from pathlib import Path

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
async def test_graph_snapshot_and_search(db):
    from mem_graph.tools.graph.graph_queries import (
        get_graph_snapshot,
        get_node_details,
        search_graph,
    )
    from mem_graph.tools.memory.memory import memory_store
    from mem_graph.tools.work.decisions import decision_record
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.tasks import task_create, task_link_decision, task_link_violation
    from mem_graph.tools.work.violations import violation_record

    project = await project_create(name="Atlas", description="Graph test project")
    project_id = project["project_id"]

    task = await task_create(project_id=project_id, title="Fix parser", description="Repair the parser edge case")
    decision = await decision_record(
        project_id=project_id,
        title="Use Ladybug",
        rationale="Graph-native storage keeps the dashboard simple.",
    )
    violation = await violation_record(
        project_id=project_id,
        audit_id="A-1",
        rule="parser:edge-case",
        severity="major",
        file_path="src/parser.py",
        description="Parser fails on empty blocks.",
    )
    await task_link_decision(task_id=task["task_id"], decision_id=decision["decision_id"])
    await task_link_violation(task_id=task["task_id"], violation_id=violation["violation_id"])
    await memory_store(
        content="The parser decision should stay visible in the graph dashboard.",
        kind="architecture",
        scope="project",
        project_id=project_id,
        conn=db,
    )

    snapshot = await get_graph_snapshot(
        project_id=project_id,
        node_types=["Project", "Task", "Decision", "Violation", "Memory"],
        depth=2,
        max_nodes=80,
    )

    node_types = {node.type for node in snapshot.nodes}
    edge_types = {edge.type for edge in snapshot.edges}
    assert {"Project", "Task", "Decision", "Violation", "Memory"}.issubset(node_types)
    assert "HAS_TASK" in edge_types
    assert "TASK_DECISION" in edge_types
    assert "TASK_VIOLATION" in edge_types

    details = await get_node_details(task["task_id"])
    assert not isinstance(details, dict)
    assert {relationship.relationship for relationship in details.relationships} >= {
        "TASK_DECISION",
        "TASK_VIOLATION",
    }

    results = await search_graph("parser edge", project_id=project_id, limit=10)
    assert any(result.id == task["task_id"] for result in results)


@pytest.mark.asyncio
async def test_dashboard_routes_respond(db):
    from mem_graph import server as server_mod
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.tasks import task_create

    project = await project_create(name="Routes", description="Dashboard route test")
    await task_create(
        project_id=project["project_id"],
        title="Check dashboard routes",
        description="Ensure the dashboard API responds with graph data.",
    )

    dashboard = server_mod._dashboard(_request("/dashboard"))
    system = server_mod._dashboard_system(_request("/dashboard/api/system"))
    styles = server_mod._dashboard_styles(_request("/dashboard/api/styles"))
    graph = await server_mod._dashboard_graph(
        _request("/dashboard/api/graph", f"project_id={project['project_id']}")
    )

    assert dashboard.status_code == 200
    assert Path(dashboard.path).name == "dashboard.html"
    assert system.status_code == 200
    assert _json(system)["telemetry"]["node_count"] >= 2
    assert styles.status_code == 200
    assert "Project" in _json(styles)["styles"]
    assert graph.status_code == 200
    payload = _json(graph)
    assert payload["nodes"]
    assert payload["available_types"]
