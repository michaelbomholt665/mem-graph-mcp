"""Shared helpers for curated CLI commands executed through CodeMode."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ESCAPE_HATCH_ENV = "MEM_GRAPH_COMMANDS_ALLOW_ESCAPES"
RAW_CYPHER_ENV = "MEM_GRAPH_COMMANDS_ALLOW_RAW_CYPHER"
RAW_CYPHER_WRITE_ENV = "MEM_GRAPH_COMMANDS_ALLOW_RAW_CYPHER_WRITE"


def canonical_command_key(command: str) -> str:
    """Return the stable dotted command key used in envelopes."""
    return ".".join(command.strip().lower().split())


def ok(
    command: str,
    data: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    *,
    status: str = "completed",
) -> dict[str, Any]:
    """Build the standard success envelope for command output."""
    return {
        "ok": True,
        "command": canonical_command_key(command),
        "status": status,
        "data": data or {},
        "warnings": warnings or [],
        "error": None,
    }


def partial(
    command: str,
    data: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a partial-success envelope."""
    return ok(command, data=data, warnings=warnings, status="partial")


def failed(
    command: str,
    error: str,
    *,
    data: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    status: str = "failed",
) -> dict[str, Any]:
    """Build the standard error envelope for command output."""
    return {
        "ok": False,
        "command": canonical_command_key(command),
        "status": status,
        "data": data or {},
        "warnings": warnings or [],
        "error": error,
    }


def accepted(
    command: str,
    task_submission: dict[str, Any],
    *,
    data: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a task-accepted envelope that preserves poll and cancel details."""
    payload = ok(command, data=data, warnings=warnings, status="accepted")
    for key in ("task_id", "poll_with", "cancel_with", "progress", "message"):
        if key in task_submission:
            payload[key] = task_submission[key]
    payload["data"]["task"] = task_submission
    return payload


def resolve_root_path(root: str | None = None) -> Path:
    """Resolve a project root, defaulting to the current working directory."""
    return Path(root or os.getcwd()).expanduser().resolve()


def env_flag(name: str) -> bool:
    value = os.getenv(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def require_gate(name: str, reason: str) -> None:
    """Require an explicit environment gate before using an escape hatch."""
    if env_flag(name):
        return
    raise PermissionError(f"{reason} Set {name}=1 to allow this command.")


def trim_text(value: str, *, limit: int = 4000) -> str:
    """Bound command output so envelopes stay compact."""
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
