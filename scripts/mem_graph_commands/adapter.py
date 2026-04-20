"""Reference helpers for external CLIs that target mem-graph execute."""

from __future__ import annotations

from typing import Any

from mem_graph.services.commands.catalog import build_command_snippet


def build_execute_arguments(
    command: str,
    arguments: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Build the exact execute-tool argument payload expected by the server."""
    payload: dict[str, Any] = {
        "code": build_command_snippet(command, arguments or {}),
    }
    if session_id:
        payload["session_id"] = session_id
    return payload


def build_execute_request(
    command: str,
    arguments: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
    request_id: str = "mem-graph-command",
) -> dict[str, Any]:
    """Build the JSON-RPC request shape external CLIs send to MCP tools/call."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": "execute",
            "arguments": build_execute_arguments(
                command,
                arguments,
                session_id=session_id,
            ),
        },
    }
