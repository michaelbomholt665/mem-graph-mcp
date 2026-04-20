from __future__ import annotations

import asyncio
from pathlib import Path

from mem_graph.sandbox.provider import SessionSandboxProvider
from mem_graph.services.commands.catalog import build_command_snippet


from mem_graph.sandbox.models.models import SandboxExecutionResult, SandboxExecutionRequest, SandboxPolicy, SandboxSession

class _DummyManager:
    async def run_in_session(
        self, session_id: str, request: SandboxExecutionRequest
    ) -> SandboxExecutionResult:  # pragma: no cover - safety guard
        raise AssertionError(
            f"run_in_session should not be called for {session_id}: {request}"
        )

    def create_session(
        self, session_id: str | None = None, *, repo_ref: str | None = None, policy: SandboxPolicy | None = None
    ) -> SandboxSession:  # pragma: no cover - safety guard
        raise AssertionError(
            f"create_session should not be called for {session_id}: {repo_ref}, {policy}"
        )


async def test_session_sandbox_provider_runs_async_snippet_with_tool_bridge() -> None:
    provider = SessionSandboxProvider(_DummyManager(), repo_root=Path.cwd())
    calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(tool_name: str, params: dict[str, object]) -> dict[str, object]:
        await asyncio.sleep(0)
        calls.append((tool_name, params))
        return {"tool_name": tool_name, "params": params}

    result = await provider.run(
        "tool = await call_tool('get_server_info', {'verbose': True})\nreturn {'tool': tool, 'value': 4}",
        inputs={"session_id": "session-1"},
        external_functions={"call_tool": call_tool},
    )

    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    assert result["result"] == {
        "tool": {
            "tool_name": "get_server_info",
            "params": {"verbose": True},
        },
        "value": 4,
    }
    assert calls == [("get_server_info", {"verbose": True})]


async def test_command_snippet_dispatches_curated_catalog_through_execute_bridge() -> None:
    provider = SessionSandboxProvider(_DummyManager(), repo_root=Path.cwd())
    calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(tool_name: str, params: dict[str, object]) -> dict[str, object]:
        await asyncio.sleep(0)
        calls.append((tool_name, params))
        if tool_name == "tools_activate":
            return {"namespace": params["namespace"], "activated": True}
        return {
            "task_id": "task-123",
            "poll_with": "get_task_status",
            "cancel_with": "cancel_task",
            "status": "queued",
            "progress": {"current": 0, "total": 100, "percentage": 0.0},
            "message": "Background task accepted.",
        }

    snippet = build_command_snippet(
        "agent audit",
        {
            "package_path": "/mock/project",
            "project_id": "memory",
        },
    )
    result = await provider.run(
        snippet,
        inputs={"session_id": "session-2"},
        external_functions={"call_tool": call_tool},
    )

    assert result["exit_code"] == 0
    assert result["result"]["ok"] is True
    assert result["result"]["command"] == "agent.audit"
    assert result["result"]["task_id"] == "task-123"
    assert calls == [
        ("tools_activate", {"namespace": "audit"}),
        (
            "audit_package",
            {
                "package_path": "/mock/project",
                "project_id": "memory",
                "report_output_path": None,
                "persist_violations": True,
                "file_extension": ".py",
                "peer_review": False,
            },
        ),
    ]
