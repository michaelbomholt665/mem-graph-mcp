from __future__ import annotations

import anyio
import pytest

from mem_graph.resources.workflows.selection.selector import select_all
from mem_graph.sandbox.manager import SessionSandboxManager
from mem_graph.sandbox.models import SandboxStatus
from mem_graph.sandbox.models.config import SandboxSettings
from mem_graph.workflows.runtime.workflow_sandbox import (
    ensure_workflow_sandbox,
    finalize_workflow_sandbox,
)


class FakePodman:
    async def start(self, session, *, repo_root):
        await anyio.sleep(0)
        session.container_id = "container-1"
        session.compose_project = "project-1"
        return session

    async def stop(self, session, *, repo_root):
        await anyio.sleep(0)
        return None


@pytest.mark.asyncio
async def test_workflow_selection_carries_sandbox_policy():
    selection = select_all("bug_fix", file_count=1)

    assert selection.sandbox_policy.enabled is True
    assert "sandbox=enabled" in selection.rationale


@pytest.mark.asyncio
async def test_workflow_sandbox_create_and_finalize(monkeypatch, tmp_path):
    monkeypatch.setenv("MEM_GRAPH_SANDBOX_ENABLED", "true")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("old\n")
    manager = SessionSandboxManager(
        SandboxSettings(enabled=True, root=tmp_path / "sandbox"),
        repo_root=repo,
        podman=FakePodman(),  # type: ignore[arg-type]
    )
    await manager.startup()
    selection = select_all("bug_fix", file_count=1)

    context = await ensure_workflow_sandbox(
        selection,
        {"session_id": "s1"},
        manager=manager,
    )

    assert context.enabled is True
    assert context.session_id == "s1"
    assert manager.get_session("s1").status == SandboxStatus.CREATED

    finalized = await finalize_workflow_sandbox(
        context,
        validation_passed=True,
        manager=manager,
    )

    assert finalized.status == "terminated"
    assert finalized.merge_back_status in {"no_changes", "merged"}
