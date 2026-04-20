"""Small Podman CLI adapter for sandbox sessions."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

import asyncio

from .compose import compose_down_argv, compose_env, compose_project_name, compose_up_argv
from ..models.config import SandboxSettings
from ..models.errors import SandboxPolicyError, SandboxProvisionError
from ..models.models import SandboxExecutionRequest, SandboxExecutionResult, SandboxSession


class PodmanAdapter:
    """Podman command boundary. All calls use argv lists, never shell=True."""

    def __init__(self, settings: SandboxSettings) -> None:
        self.settings = settings

    async def start(self, session: SandboxSession, *, repo_root: Path) -> SandboxSession:
        self._validate_mount(session.snapshot_path, self.settings.resolved_root())
        self._validate_mount(session.workspace_path, self.settings.resolved_root())
        project = compose_project_name(session.session_id)
        compose_file = self.settings.resolved_compose_file(repo_root)
        env = os.environ.copy()
        env.update(compose_env(session))
        proc = await asyncio.to_thread(
            _run_completed,
            compose_up_argv(self.settings.compose_command, compose_file, project),
            env,
            self.settings.exec_timeout_seconds,
        )
        if proc.returncode != 0:
            raise SandboxProvisionError(_limited(proc.stderr))
        session.compose_project = project
        session.container_id = await self._container_id(project)
        return session

    async def exec(
        self,
        session: SandboxSession,
        request: SandboxExecutionRequest,
    ) -> SandboxExecutionResult:
        if not session.container_id:
            raise SandboxProvisionError("Session container has not been provisioned.")
        command = request.command or _python_command(request.code or "")
        timeout = (
            request.timeout_seconds
            or session.policy.resource_limits.exec_timeout_seconds
            or self.settings.exec_timeout_seconds
        )
        output_limit = (
            request.output_limit_bytes
            or session.policy.resource_limits.output_limit_bytes
            or self.settings.output_limit_bytes
        )
        argv = [
            self.settings.podman_binary,
            "exec",
            "--workdir",
            request.cwd,
            *self._env_args(request.env),
            session.container_id,
            *command,
        ]
        started = time.monotonic()
        try:
            proc = await asyncio.to_thread(_run_completed, argv, None, timeout)
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            return SandboxExecutionResult(
                stdout=_decode_limited(exc.stdout, output_limit),
                stderr=_decode_limited(exc.stderr, output_limit),
                exit_code=124,
                timed_out=True,
                command=command,
                duration_seconds=time.monotonic() - started,
                session_id=session.session_id,
                container_id=session.container_id,
            )
        return SandboxExecutionResult(
            stdout=_limited(proc.stdout, output_limit),
            stderr=_limited(proc.stderr, output_limit),
            exit_code=proc.returncode,
            timed_out=timed_out,
            command=command,
            duration_seconds=time.monotonic() - started,
            session_id=session.session_id,
            container_id=session.container_id,
        )

    async def stop(self, session: SandboxSession, *, repo_root: Path) -> None:
        project = session.compose_project or compose_project_name(session.session_id)
        compose_file = self.settings.resolved_compose_file(repo_root)
        await asyncio.to_thread(
            _run_completed,
            compose_down_argv(self.settings.compose_command, compose_file, project),
            None,
            self.settings.exec_timeout_seconds,
        )

    async def inspect_running(self, session: SandboxSession) -> bool:
        if not session.container_id:
            return False
        proc = await asyncio.to_thread(
            _run_completed,
            [
                self.settings.podman_binary,
                "inspect",
                "-f",
                "{{.State.Running}}",
                session.container_id,
            ],
            None,
            self.settings.exec_timeout_seconds,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    async def _container_id(self, project_name: str) -> str:
        proc = await asyncio.to_thread(
            _run_completed,
            [
                self.settings.podman_binary,
                "ps",
                "-q",
                "--filter",
                f"label=io.podman.compose.project={project_name}",
                "--filter",
                "label=mem_graph.sandbox=true",
            ],
            None,
            self.settings.exec_timeout_seconds,
        )
        return proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""

    def _validate_mount(self, path: Path, allowed_root: Path) -> None:
        resolved = path.expanduser().resolve()
        root = allowed_root.expanduser().resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SandboxPolicyError(
                f"Sandbox mount path is outside allowed root: {resolved}"
            ) from exc

    @staticmethod
    def _env_args(env: Mapping[str, str]) -> list[str]:
        args: list[str] = []
        for key, value in sorted(env.items()):
            if key.startswith(("MEM_GRAPH_", "PATH", "HOME")):
                continue
            args.extend(["--env", f"{key}={value}"])
        return args


def _python_command(code: str) -> list[str]:
    return ["python", "-c", code]


def _run_completed(
    argv: list[str],
    env: dict[str, str] | None,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _limited(value: str, limit: int = 128_000) -> str:
    if len(value.encode("utf-8", errors="replace")) <= limit:
        return value
    return value.encode("utf-8", errors="replace")[:limit].decode(
        "utf-8", errors="replace"
    )


def _decode_limited(value: bytes | str | None, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _limited(value, limit)
    return value[:limit].decode("utf-8", errors="replace")
