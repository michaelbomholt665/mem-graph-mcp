from __future__ import annotations

from mem_graph.sandbox.filesystem.snapshots import (
    create_repo_snapshot,
    create_session_layout,
    initialize_workspace,
    merge_workspace_back,
)


def test_snapshot_filters_sensitive_runtime_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('ok')\n")
    (repo / ".env").write_text("SECRET=1\n")
    (repo / "data").mkdir()
    (repo / "data" / "db.lbug").write_text("db")
    root = tmp_path / "sandbox"
    _, snapshot, workspace = create_session_layout(root, "s1")

    create_repo_snapshot(repo, snapshot)
    initialize_workspace(snapshot, workspace)

    assert (snapshot / "app.py").exists()
    assert not (snapshot / ".env").exists()
    assert not (snapshot / "data").exists()
    assert (workspace / "app.py").exists()


def test_merge_workspace_back_clean_change(tmp_path):
    host = tmp_path / "repo"
    host.mkdir()
    (host / "app.py").write_text("old\n")
    root = tmp_path / "sandbox"
    _, snapshot, workspace = create_session_layout(root, "s1")
    create_repo_snapshot(host, snapshot)
    initialize_workspace(snapshot, workspace)
    (workspace / "app.py").write_text("new\n")

    result = merge_workspace_back(
        snapshot_path=snapshot,
        workspace_path=workspace,
        host_root=host,
    )

    assert result.status == "merged"
    assert result.changed_files == ["app.py"]
    assert (host / "app.py").read_text() == "new\n"
