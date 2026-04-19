from __future__ import annotations

import anyio
import pytest

from mem_graph.sandbox.config import SandboxSettings
from mem_graph.sandbox.manager import SessionSandboxManager
from mem_graph.sandbox.models import (
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxStatus,
)


class FakePodman:
    def __init__(self) -> None:
        self.starts = 0
        self.stops = 0

    async def start(self, session, *, repo_root):
        self.starts += 1
        session.container_id = "container-1"
        session.compose_project = "project-1"
        return session

    async def exec(self, session, request):
        return SandboxExecutionResult(
            stdout="ok",
            exit_code=0,
            session_id=session.session_id,
            container_id=session.container_id,
            command=request.command,
        )

    async def stop(self, session, *, repo_root):
        self.stops += 1


@pytest.mark.asyncio
async def test_manager_lifecycle_lazy_start(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('ok')\n")
    fake = FakePodman()
    manager = SessionSandboxManager(
        SandboxSettings(enabled=True, root=tmp_path / "sandbox"),
        repo_root=repo,
        podman=fake,
    )
    await manager.startup()
    session = await manager.create_session("s1")

    assert session.status == SandboxStatus.CREATED
    result = await manager.run_in_session("s1", SandboxExecutionRequest(command=["true"]))

    assert result.stdout == "ok"
    assert manager.get_session("s1").status == SandboxStatus.ACTIVE
    assert fake.starts == 1
    destroyed = await manager.destroy_session("s1")
    assert destroyed.status == SandboxStatus.TERMINATED
    assert fake.stops == 1


@pytest.mark.asyncio
async def test_manager_concurrent_first_use_starts_once(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('ok')\n")
    fake = FakePodman()
    manager = SessionSandboxManager(
        SandboxSettings(enabled=True, root=tmp_path / "sandbox"),
        repo_root=repo,
        podman=fake,
    )
    await manager.startup()
    await manager.create_session("s1")

    async with anyio.create_task_group() as tg:
        for _ in range(5):
            tg.start_soon(manager.run_in_session, "s1", SandboxExecutionRequest(command=["true"]))

    assert fake.starts == 1
