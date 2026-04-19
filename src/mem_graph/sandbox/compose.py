"""Podman compose argument construction."""

from __future__ import annotations

import re
from pathlib import Path

from .errors import SandboxPolicyError
from .models import SandboxSession

_SESSION_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def compose_project_name(session_id: str) -> str:
    if not _SESSION_RE.fullmatch(session_id):
        raise SandboxPolicyError(f"Invalid sandbox session id: {session_id!r}")
    return f"memgraph-sandbox-{session_id.lower().replace('_', '-')}"[:63]


def compose_env(session: SandboxSession) -> dict[str, str]:
    policy = session.policy
    return {
        "MEM_GRAPH_SANDBOX_IMAGE": policy.image,
        "MEM_GRAPH_SANDBOX_SESSION_ID": session.session_id,
        "MEM_GRAPH_SANDBOX_REPO": str(session.snapshot_path),
        "MEM_GRAPH_SANDBOX_WORKSPACE": str(session.workspace_path),
        "MEM_GRAPH_SANDBOX_NETWORK": policy.network,
        "MEM_GRAPH_SANDBOX_MEMORY": policy.resource_limits.memory,
        "MEM_GRAPH_SANDBOX_CPUS": policy.resource_limits.cpus,
    }


def compose_up_argv(
    compose_command: tuple[str, ...],
    compose_file: Path,
    project_name: str,
) -> list[str]:
    return [
        *compose_command,
        "-f",
        str(compose_file),
        "-p",
        project_name,
        "up",
        "-d",
        "--remove-orphans",
    ]


def compose_down_argv(
    compose_command: tuple[str, ...],
    compose_file: Path,
    project_name: str,
) -> list[str]:
    return [
        *compose_command,
        "-f",
        str(compose_file),
        "-p",
        project_name,
        "down",
        "--remove-orphans",
        "--volumes",
    ]
