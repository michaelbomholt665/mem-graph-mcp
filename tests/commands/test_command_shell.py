from __future__ import annotations

import asyncio

import pytest

from mem_graph.services.commands import command_shell


@pytest.mark.asyncio
async def test_run_allowlisted_command_rejects_unknown_argv():
    with pytest.raises(ValueError):
        await command_shell.run_allowlisted_command(("python", "-V"))


@pytest.mark.asyncio
async def test_shell_execute_requires_escape_hatch_gate(monkeypatch):
    monkeypatch.delenv("MEM_GRAPH_COMMANDS_ALLOW_ESCAPES", raising=False)

    response = await command_shell.shell_execute(["uv", "run", "pytest", "-q"])

    assert response["ok"] is False
    assert "disabled by default" in response["error"]


@pytest.mark.asyncio
async def test_toolchain_python_reports_optional_scanner_warnings(monkeypatch):
    async def fake_run(argv, *, root=None, timeout_seconds=None, optional=None):
        await asyncio.sleep(0)
        if argv[0] in {"semgrep", "trivy"}:
            return {
                "argv": list(argv),
                "status": "skipped",
                "exit_code": None,
                "timed_out": False,
                "stdout": "",
                "stderr": f"Executable not found: {argv[0]}",
                "duration_seconds": 0.0,
            }
        return {
            "argv": list(argv),
            "status": "completed",
            "exit_code": 0,
            "timed_out": False,
            "stdout": "ok",
            "stderr": "",
            "duration_seconds": 0.1,
        }

    monkeypatch.setattr(command_shell, "run_allowlisted_command", fake_run)

    response = await command_shell.toolchain_python(root=".")

    assert response["ok"] is True
    assert response["status"] == "partial"
    assert "Executable not found: semgrep" in response["warnings"]
