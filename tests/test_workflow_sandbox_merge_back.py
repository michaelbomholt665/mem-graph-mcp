from __future__ import annotations

import pytest

from mem_graph.sandbox.filesystem.snapshots import (
    create_repo_snapshot,
    create_session_layout,
    initialize_workspace,
    merge_workspace_back,
)
from mem_graph.sandbox.models.errors import SandboxMergeConflictError


def test_merge_back_blocks_host_conflict(tmp_path):
    host = tmp_path / "repo"
    host.mkdir()
    (host / "app.py").write_text("old\n")
    _, snapshot, workspace = create_session_layout(tmp_path / "sandbox", "s1")
    create_repo_snapshot(host, snapshot)
    initialize_workspace(snapshot, workspace)
    (workspace / "app.py").write_text("sandbox\n")
    (host / "app.py").write_text("host changed\n")

    with pytest.raises(SandboxMergeConflictError):
        merge_workspace_back(
            snapshot_path=snapshot,
            workspace_path=workspace,
            host_root=host,
        )


def test_merge_back_excludes_runtime_files(tmp_path):
    host = tmp_path / "repo"
    host.mkdir()
    (host / "app.py").write_text("old\n")
    _, snapshot, workspace = create_session_layout(tmp_path / "sandbox", "s1")
    create_repo_snapshot(host, snapshot)
    initialize_workspace(snapshot, workspace)
    (workspace / ".env").write_text("SECRET=1\n")

    result = merge_workspace_back(
        snapshot_path=snapshot,
        workspace_path=workspace,
        host_root=host,
    )

    assert result.status == "no_changes"
    assert not (host / ".env").exists()
