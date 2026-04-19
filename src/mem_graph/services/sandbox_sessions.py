"""Service accessors for the process-wide sandbox manager."""

from __future__ import annotations

from pathlib import Path

from ..sandbox.config import SandboxSettings, get_sandbox_settings
from ..sandbox.manager import SessionSandboxManager, get_sandbox_manager, set_sandbox_manager


def configure_sandbox_manager(
    *,
    settings: SandboxSettings | None = None,
    repo_root: Path | None = None,
) -> SessionSandboxManager:
    manager = SessionSandboxManager(settings or get_sandbox_settings(), repo_root=repo_root)
    set_sandbox_manager(manager)
    return manager


def sandbox_manager() -> SessionSandboxManager:
    return get_sandbox_manager()
