from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from mem_graph.services.commands.catalog import build_command_snippet, dispatch_command
from mem_graph.services.commands.command_db import list_templates

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.mem_graph_commands.adapter import build_execute_request


async def test_dispatch_agent_audit_activates_namespace_and_preserves_task_payload() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(tool_name: str, params: dict[str, object]) -> dict[str, object]:
        await asyncio.sleep(0)
        calls.append((tool_name, params))
        if tool_name == "tools_activate":
            return {"namespace": params["namespace"], "activated": True}
        return {
            "task_id": "task-9",
            "poll_with": "get_task_status",
            "cancel_with": "cancel_task",
            "status": "queued",
            "progress": {"current": 0, "total": 100, "percentage": 0.0},
            "message": "Background task accepted.",
        }

    response = await dispatch_command(
        "agent audit",
        {
            "package_path": "/mock/repo",
            "project_id": "memory",
        },
        call_tool=call_tool,
    )

    assert response["ok"] is True
    assert response["task_id"] == "task-9"
    assert calls[0] == ("tools_activate", {"namespace": "audit"})
    assert calls[1][0] == "audit_package"


async def test_python_repl_command_respects_escape_hatch_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEM_GRAPH_COMMANDS_ALLOW_ESCAPES", raising=False)

    response = await dispatch_command("python repl", {"code": "return 7"})

    assert response["ok"] is False
    assert "disabled by default" in response["error"]


def test_build_command_snippet_and_adapter_request_shape() -> None:
    snippet = build_command_snippet("db inspect", {"inspect_set": "schema"})
    request = build_execute_request(
        "db inspect",
        {"inspect_set": "schema"},
        session_id="session-1",
    )

    assert "dispatch_command" in snippet
    assert request == {
        "jsonrpc": "2.0",
        "id": "mem-graph-command",
        "method": "tools/call",
        "params": {
            "name": "execute",
            "arguments": {
                "code": snippet,
                "session_id": "session-1",
            },
        },
    }


def test_db_templates_are_exposed_for_cli_help() -> None:
    template_names = {template["name"] for template in list_templates()}

    assert {
        "schema.counts",
        "schema.indexes",
        "projects.list",
        "evals.recent",
    }.issubset(template_names)
