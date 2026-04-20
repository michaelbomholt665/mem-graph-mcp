"""Workflow-facing sandbox lifecycle helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
import asyncio
from uuid import uuid4

from ...resources.workflows.models import WorkflowSandboxPolicy
from ...resources.workflows.selector import WorkflowSelection
from ...sandbox.models.config import get_sandbox_settings
from ...sandbox.models.errors import SandboxDisabledError
from ...sandbox.manager import SessionSandboxManager
from ...sandbox.models.models import SandboxPolicy, SandboxResourceLimits, SandboxSession
from ...services.sandbox_sessions import sandbox_manager


@dataclass
class WorkflowSandboxContext:
    session_id: str = ""
    enabled: bool = False
    status: str = "disabled"
    workspace_path: str = ""
    merge_back_status: str = ""
    changed_files: list[str] = field(default_factory=list)
    error: str = ""

    def artifact(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "session_id": self.session_id,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "merge_back_status": self.merge_back_status,
            "changed_files": self.changed_files,
            "error": self.error,
        }


def sandbox_policy_from_workflow(policy: WorkflowSandboxPolicy) -> SandboxPolicy:
    return SandboxPolicy(
        enabled=policy.enabled,
        image=policy.image,
        network=policy.network,
        merge_back=policy.merge_back,
        retain_artifacts=policy.retain_artifacts,
        resource_limits=SandboxResourceLimits(
            memory=policy.memory,
            cpus=policy.cpus,
            exec_timeout_seconds=policy.exec_timeout_seconds,
            session_ttl_seconds=policy.session_ttl_seconds,
        ),
    )


async def ensure_workflow_sandbox(
    selection: WorkflowSelection,
    task_context: dict[str, Any] | None = None,
    *,
    manager: SessionSandboxManager | None = None,
) -> WorkflowSandboxContext:
    settings = get_sandbox_settings()
    if not settings.enabled or not selection.sandbox_policy.enabled:
        return WorkflowSandboxContext()
    session_id = str((task_context or {}).get("session_id") or uuid4())
    return await start_workflow_sandbox(
        session_id=session_id,
        selection=selection,
        manager=manager,
    )


async def start_workflow_sandbox(
    *,
    session_id: str,
    selection: WorkflowSelection,
    manager: SessionSandboxManager | None = None,
) -> WorkflowSandboxContext:
    await asyncio.sleep(0)
    mgr = manager or sandbox_manager()
    policy = sandbox_policy_from_workflow(selection.sandbox_policy)
    try:
        session = mgr.create_session(
            session_id,
            repo_ref=selection.workflow.key,
            policy=policy,
        )
    except SandboxDisabledError:
        return WorkflowSandboxContext()
    return _context_from_session(session, enabled=True)


async def finalize_workflow_sandbox(
    context: WorkflowSandboxContext,
    *,
    validation_passed: bool,
    manager: SessionSandboxManager | None = None,
) -> WorkflowSandboxContext:
    if not context.enabled or not context.session_id:
        return context
    mgr = manager or sandbox_manager()
    try:
        session = mgr.get_session(context.session_id)
        if validation_passed and session.policy.merge_back:
            merge = mgr.merge_back(context.session_id)
            context.merge_back_status = str(merge["status"])
            context.changed_files = list(cast(list[str], merge["changed_files"]))
        else:
            context.merge_back_status = "skipped"
        destroyed = await mgr.destroy_session(context.session_id)
        context.status = destroyed.status.value
        return context
    except Exception as exc:  # noqa: BLE001
        context.error = str(exc)
        context.status = "failed"
        return context


async def abort_workflow_sandbox(
    context: WorkflowSandboxContext,
    *,
    manager: SessionSandboxManager | None = None,
) -> WorkflowSandboxContext:
    if not context.enabled or not context.session_id:
        return context
    mgr = manager or sandbox_manager()
    try:
        destroyed = await mgr.destroy_session(context.session_id)
        context.status = destroyed.status.value
        context.merge_back_status = "aborted"
    except Exception as exc:  # noqa: BLE001
        context.status = "failed"
        context.error = str(exc)
    return context


def _context_from_session(
    session: SandboxSession,
    *,
    enabled: bool,
) -> WorkflowSandboxContext:
    return WorkflowSandboxContext(
        session_id=session.session_id,
        enabled=enabled,
        status=session.status.value,
        workspace_path=str(session.workspace_path),
    )
