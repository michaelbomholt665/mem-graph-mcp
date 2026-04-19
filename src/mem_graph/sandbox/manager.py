"""Session sandbox manager with lazy Podman provisioning."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from .config import SandboxSettings, get_sandbox_settings
from .errors import SandboxDisabledError, SandboxNotFoundError
from .models import (
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxPolicy,
    SandboxSession,
    SandboxStatus,
)
from .podman import PodmanAdapter
from .snapshots import (
    cleanup_session_paths,
    create_repo_snapshot,
    create_session_layout,
    initialize_workspace,
    merge_workspace_back,
)

logger = logging.getLogger(__name__)
_MANAGER: "SessionSandboxManager | None" = None


class SessionSandboxManager:
    """Owns per-session metadata, workspace layout, and container lifecycle."""

    def __init__(
        self,
        settings: SandboxSettings | None = None,
        *,
        repo_root: Path | None = None,
        podman: PodmanAdapter | None = None,
    ) -> None:
        self.settings = settings or get_sandbox_settings()
        self.repo_root = (repo_root or Path.cwd()).expanduser().resolve()
        self.root = self.settings.resolved_root()
        self.podman = podman or PodmanAdapter(self.settings)
        self._sessions: dict[str, SandboxSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    async def startup(self) -> None:
        await asyncio.sleep(0)
        self.root.mkdir(parents=True, exist_ok=True)
        self.recover_metadata()

    async def shutdown(self) -> None:
        for session_id in tuple(self._sessions.keys()):
            session = self._sessions[session_id]
            if session.status in {SandboxStatus.CREATED, SandboxStatus.ACTIVE, SandboxStatus.FAILED}:
                await self.destroy_session(session_id)

    def recover_metadata(self) -> None:
        sessions_root = self.root / "sessions"
        if not sessions_root.exists():
            return
        for metadata in sessions_root.glob("*/metadata.json"):
            try:
                session = SandboxSession.model_validate_json(metadata.read_text())
            except Exception as exc:  # noqa: BLE001
                logger.warning("sandbox_metadata_recover_failed path=%s error=%s", metadata, exc)
                continue
            if session.status != SandboxStatus.TERMINATED:
                self._sessions[session.session_id] = session

    def create_session(
        self,
        session_id: str | None = None,
        *,
        repo_ref: str | None = None,
        policy: SandboxPolicy | None = None,
    ) -> SandboxSession:
        if not self.enabled:
            raise SandboxDisabledError("Sandbox execution is disabled.")
        session_id = session_id or str(uuid4())
        policy = policy or SandboxPolicy(
            enabled=True,
            image=self.settings.image,
            network=self.settings.network,
            snapshot_policy=self.settings.snapshot_policy,
        )
        if not policy.enabled:
            policy = policy.model_copy(update={"enabled": True})
        _, snapshot, workspace = create_session_layout(self.root, session_id)
        create_repo_snapshot(self.repo_root, snapshot)
        initialize_workspace(snapshot, workspace)
        now = datetime.now(UTC)
        session = SandboxSession(
            session_id=session_id,
            repo_ref=repo_ref or str(self.repo_root),
            snapshot_path=snapshot,
            workspace_path=workspace,
            policy=policy,
            expires_at=now + timedelta(seconds=policy.resource_limits.session_ttl_seconds),
        )
        self._sessions[session_id] = session
        self._locks.setdefault(session_id, asyncio.Lock())
        self._write_metadata(session)
        logger.info("sandbox_session_created session_id=%s", session_id)
        return session

    async def run_in_session(
        self,
        session_id: str,
        request: SandboxExecutionRequest,
    ) -> SandboxExecutionResult:
        if not self.enabled:
            raise SandboxDisabledError("Sandbox execution is disabled.")
        session = self.get_session(session_id)
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            if session.status == SandboxStatus.CREATED:
                try:
                    session = await self.podman.start(session, repo_root=self.repo_root)
                    session.status = SandboxStatus.ACTIVE
                    self._write_metadata(session)
                except Exception as exc:
                    session.status = SandboxStatus.FAILED
                    session.failure_detail = str(exc)
                    self._write_metadata(session)
                    raise
            if session.status != SandboxStatus.ACTIVE:
                raise SandboxNotFoundError(
                    f"Sandbox session {session_id!r} is not active: {session.status.value}"
                )
        result = await self.podman.exec(session, request)
        session.touch()
        if result.exit_code == 137:
            session.status = SandboxStatus.FAILED
            session.failure_detail = "Container exited with code 137 (possible OOM)."
        self._write_metadata(session)
        logger.info(
            "sandbox_exec_completed session_id=%s exit_code=%s timed_out=%s duration=%.3f",
            session_id,
            result.exit_code,
            result.timed_out,
            result.duration_seconds,
        )
        return result

    def merge_back(self, session_id: str) -> dict[str, object]:
        session = self.get_session(session_id)
        try:
            result = merge_workspace_back(
                snapshot_path=session.snapshot_path,
                workspace_path=session.workspace_path,
                host_root=self.repo_root,
            )
        except Exception:
            session.merge_back_status = "conflict"
            self._write_metadata(session)
            raise
        session.merge_back_status = result.status
        session.changed_files = result.changed_files
        self._write_metadata(session)
        return result.model_dump(mode="json")

    async def destroy_session(self, session_id: str) -> SandboxSession:
        session = self.get_session(session_id)
        if session.status == SandboxStatus.TERMINATED:
            return session
        session.status = SandboxStatus.TERMINATING
        self._write_metadata(session)
        try:
            if session.container_id or session.compose_project:
                await self.podman.stop(session, repo_root=self.repo_root)
            if not session.policy.retain_artifacts and not self.settings.retain_artifacts:
                cleanup_session_paths(self.root, session_id)
            session.status = SandboxStatus.TERMINATED
            session.cleanup_error = ""
        except Exception as exc:  # noqa: BLE001
            session.status = SandboxStatus.FAILED
            session.cleanup_error = str(exc)
            logger.warning("sandbox_cleanup_failed session_id=%s error=%s", session_id, exc)
        self._write_metadata(session)
        logger.info("sandbox_session_destroyed session_id=%s status=%s", session_id, session.status.value)
        return session

    async def cleanup_stale(self) -> list[str]:
        cleaned: list[str] = []
        now = datetime.now(UTC)
        for session_id, session in tuple(self._sessions.items()):
            if session.status != SandboxStatus.TERMINATED and session.expired(now):
                await self.destroy_session(session_id)
                cleaned.append(session_id)
        return cleaned

    def get_session(self, session_id: str) -> SandboxSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise SandboxNotFoundError(f"Sandbox session not found: {session_id}") from exc

    def list_sessions(self) -> list[SandboxSession]:
        return sorted(self._sessions.values(), key=lambda item: item.created_at)

    def _write_metadata(self, session: SandboxSession) -> None:
        path = session.workspace_path.parent / "metadata.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")


def get_sandbox_manager() -> SessionSandboxManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = SessionSandboxManager()
    return _MANAGER


def set_sandbox_manager(manager: SessionSandboxManager | None) -> None:
    global _MANAGER
    _MANAGER = manager
