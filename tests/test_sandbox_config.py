from __future__ import annotations

from mem_graph.sandbox.models.config import SandboxSettings


def test_sandbox_settings_defaults(monkeypatch):
    for name in [
        "MEM_GRAPH_SANDBOX_ENABLED",
        "MEM_GRAPH_SANDBOX_BACKEND",
        "MEM_GRAPH_SANDBOX_ROOT",
    ]:
        monkeypatch.delenv(name, raising=False)

    settings = SandboxSettings.from_env()

    assert settings.enabled is False
    assert settings.backend == "podman"
    assert settings.network == "none"
    assert settings.memory == "1g"
    assert settings.exec_timeout_seconds == 30


def test_sandbox_settings_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("MEM_GRAPH_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("MEM_GRAPH_SANDBOX_ROOT", str(tmp_path))
    monkeypatch.setenv("MEM_GRAPH_SANDBOX_MEMORY", "2g")
    monkeypatch.setenv("MEM_GRAPH_SANDBOX_CPUS", "4")

    settings = SandboxSettings.from_env()

    assert settings.enabled is True
    assert settings.root == tmp_path
    assert settings.memory == "2g"
    assert settings.cpus == "4"
