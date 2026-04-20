from __future__ import annotations

from pathlib import Path

import pytest

from mem_graph.sandbox.containers.compose import compose_down_argv, compose_project_name, compose_up_argv
from mem_graph.sandbox.models.config import SandboxSettings
from mem_graph.sandbox.models.errors import SandboxPolicyError
from mem_graph.sandbox.containers.podman import PodmanAdapter


def test_compose_project_name_validates_session_id():
    assert compose_project_name("ABC-123").startswith("memgraph-sandbox-abc-123")
    with pytest.raises(SandboxPolicyError):
        compose_project_name("../../bad")


def test_compose_argv_contains_project_and_no_shell():
    up = compose_up_argv(("podman", "compose"), Path("docker-compose.sandbox.yml"), "p")
    down = compose_down_argv(("podman", "compose"), Path("docker-compose.sandbox.yml"), "p")

    assert up[:2] == ["podman", "compose"]
    assert "up" in up
    assert "down" in down
    assert all(";" not in part for part in [*up, *down])


def test_podman_mount_validation_blocks_outside_root(tmp_path):
    adapter = PodmanAdapter(SandboxSettings(enabled=True, root=tmp_path))
    with pytest.raises(SandboxPolicyError):
        adapter._validate_mount(Path("/tmp/outside"), tmp_path / "allowed")
