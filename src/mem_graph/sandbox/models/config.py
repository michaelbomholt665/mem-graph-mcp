"""Typed configuration for per-session sandbox execution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


SandboxBackend = Literal["podman"]
SnapshotPolicy = Literal["per_repo", "per_branch", "per_workflow"]
NetworkMode = Literal["none", "bridge"]


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SandboxSettings:
    """Environment-backed settings for sandbox lifecycle and policy."""

    enabled: bool = False
    backend: SandboxBackend = "podman"
    image: str = "python:3.14-slim"
    compose_file: Path = Path("docker-compose.sandbox.yml")
    root: Path = Path("./data/sandbox")
    snapshot_policy: SnapshotPolicy = "per_workflow"
    network: NetworkMode = "none"
    memory: str = "1g"
    cpus: str = "2"
    exec_timeout_seconds: int = 30
    session_ttl_seconds: int = 3600
    cleanup_interval_seconds: int = 300
    output_limit_bytes: int = 128_000
    retain_artifacts: bool = False
    podman_binary: str = "podman"
    compose_command: tuple[str, ...] = ("podman", "compose")

    @classmethod
    def from_env(cls) -> "SandboxSettings":
        compose_runner = os.getenv("MEM_GRAPH_SANDBOX_COMPOSE_COMMAND", "podman compose")
        return cls(
            enabled=_bool_env("MEM_GRAPH_SANDBOX_ENABLED", False),
            backend=os.getenv("MEM_GRAPH_SANDBOX_BACKEND", "podman"),  # type: ignore[arg-type]
            image=os.getenv("MEM_GRAPH_SANDBOX_IMAGE", "python:3.14-slim"),
            compose_file=Path(
                os.getenv(
                    "MEM_GRAPH_SANDBOX_COMPOSE_FILE",
                    "docker-compose.sandbox.yml",
                )
            ),
            root=Path(os.getenv("MEM_GRAPH_SANDBOX_ROOT", "./data/sandbox")),
            snapshot_policy=os.getenv(
                "MEM_GRAPH_SANDBOX_SNAPSHOT_POLICY", "per_workflow"
            ),  # type: ignore[arg-type]
            network=os.getenv("MEM_GRAPH_SANDBOX_NETWORK", "none"),  # type: ignore[arg-type]
            memory=os.getenv("MEM_GRAPH_SANDBOX_MEMORY", "1g"),
            cpus=os.getenv("MEM_GRAPH_SANDBOX_CPUS", "2"),
            exec_timeout_seconds=int(
                os.getenv("MEM_GRAPH_SANDBOX_EXEC_TIMEOUT_SECONDS", "30")
            ),
            session_ttl_seconds=int(
                os.getenv("MEM_GRAPH_SANDBOX_SESSION_TTL_SECONDS", "3600")
            ),
            cleanup_interval_seconds=int(
                os.getenv("MEM_GRAPH_SANDBOX_CLEANUP_INTERVAL_SECONDS", "300")
            ),
            output_limit_bytes=int(
                os.getenv("MEM_GRAPH_SANDBOX_OUTPUT_LIMIT_BYTES", "128000")
            ),
            retain_artifacts=_bool_env("MEM_GRAPH_SANDBOX_RETAIN_ARTIFACTS", False),
            podman_binary=os.getenv("MEM_GRAPH_SANDBOX_PODMAN_BINARY", "podman"),
            compose_command=tuple(compose_runner.split()),
        )

    def resolved_root(self) -> Path:
        return self.root.expanduser().resolve()

    def resolved_compose_file(self, base_dir: Path | None = None) -> Path:
        path = self.compose_file.expanduser()
        if path.is_absolute():
            return path
        return ((base_dir or Path.cwd()) / path).resolve()


def get_sandbox_settings() -> SandboxSettings:
    """Return sandbox settings from the current process environment."""

    return SandboxSettings.from_env()
