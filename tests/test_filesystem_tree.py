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


def _find_node(node: dict, relative_path: str) -> dict | None:
    if node.get("relative_path") == relative_path:
        return node
    for child in node.get("children", []):
        found = _find_node(child, relative_path)
        if found is not None:
            return found
    return None


@pytest.mark.asyncio
async def test_get_file_tree_orders_and_aggregates(db, tmp_path):
    from mem_graph.tools.filesystem.tree import get_file_tree
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.violations import violation_record

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    project = await project_create(name="Files", description="Tree test", repo_path=str(repo_root))
    project_id = project["project_id"]

    (repo_root / "docs").mkdir()
    src_dir = repo_root / "src"
    src_dir.mkdir()
    utils_dir = src_dir / "utils"
    utils_dir.mkdir()

    (repo_root / "README.md").write_text("hello\n")
    (repo_root / ".secret").write_text("ignore\n")
    (src_dir / "app.py").write_text("print('app')\n")
    (utils_dir / "helpers.py").write_text("print('helpers')\n")

    await violation_record(
        project_id=project_id,
        audit_id="A-1",
        rule="auth:missing-check",
        severity="major",
        file_path="src/app.py",
        description="Missing auth validation",
    )
    await violation_record(
        project_id=project_id,
        audit_id="A-2",
        rule="util:stale-helper",
        severity="minor",
        file_path="src/utils/helpers.py",
        description="Helper should be simplified",
    )

    tree = await get_file_tree(root_path=str(repo_root), project_id=project_id)
    assert not isinstance(tree, dict)

    root_payload = tree.model_dump(mode="json")
    assert [child["name"] for child in root_payload["children"]] == ["docs", "src", "README.md"]
    assert _find_node(root_payload, ".secret") is None

    src_node = _find_node(root_payload, "src")
    assert src_node is not None
    assert src_node["violation_count"] == 2

    app_node = _find_node(root_payload, "src/app.py")
    assert app_node is not None
    assert app_node["violation_count"] == 1
    assert app_node["last_audited"] is not None


@pytest.mark.asyncio
async def test_file_tree_routes_respond(db, tmp_path):
    from mem_graph import server as server_mod
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.violations import violation_record

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    project = await project_create(name="Routes", description="Explorer route test", repo_path=str(repo_root))
    project_id = project["project_id"]

    src_dir = repo_root / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("print('app')\n")
    await violation_record(
        project_id=project_id,
        audit_id="A-9",
        rule="route:test",
        severity="major",
        file_path="src/app.py",
        description="Route explorer test",
    )

    tree_page = server_mod._file_tree(_request("/file-tree"))
    tree_api = await server_mod._file_tree_data(
        _request(
            "/file-tree/api/tree",
            f"root_path={repo_root}&project_id={project_id}",
        )
    )
    detail_api = await server_mod._file_tree_violations(
        _request(
            "/file-tree/api/violations",
            f"root_path={repo_root}&project_id={project_id}&file_path=src/app.py",
        )
    )

    assert tree_page.status_code == 200
    assert Path(tree_page.path).name == "file-tree.html"
    assert tree_api.status_code == 200
    assert _json(tree_api)["children"]
    assert detail_api.status_code == 200
    detail_payload = _json(detail_api)
    assert detail_payload["violation_count"] == 1
    assert detail_payload["violations"][0]["rule"] == "route:test"
