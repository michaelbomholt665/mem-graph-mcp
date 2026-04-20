"""Pydantic models for sandbox sessions and execution results."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class SandboxStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    FAILED = "failed"
    TERMINATING = "terminating"
    TERMINATED = "terminated"


class SandboxResourceLimits(BaseModel):
    memory: str = "1g"
    cpus: str = "2"
    exec_timeout_seconds: int = Field(default=30, ge=1)
    session_ttl_seconds: int = Field(default=3600, ge=1)
    output_limit_bytes: int = Field(default=128_000, ge=1024)


class SandboxPolicy(BaseModel):
    enabled: bool = False
    backend: Literal["podman"] = "podman"
    image: str = "python:3.14-slim"
    network: Literal["none", "bridge"] = "none"
    snapshot_policy: Literal["per_repo", "per_branch", "per_workflow"] = "per_workflow"
    merge_back: bool = False
    retain_artifacts: bool = False
    resource_limits: SandboxResourceLimits = Field(
        default_factory=SandboxResourceLimits
    )


class SandboxSession(BaseModel):
    session_id: str
    repo_ref: str
    snapshot_path: Path
    workspace_path: Path
    status: SandboxStatus = SandboxStatus.CREATED
    container_id: str | None = None
    compose_project: str | None = None
    policy: SandboxPolicy = Field(default_factory=SandboxPolicy)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(seconds=3600)
    )
    cleanup_error: str = ""
    failure_detail: str = ""
    merge_back_status: str = ""
    changed_files: list[str] = Field(default_factory=list)

    def touch(self) -> None:
        self.last_used_at = datetime.now(UTC)

    def expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at


class SandboxExecutionRequest(BaseModel):
    command: list[str] = Field(default_factory=list)
    code: str | None = None
    cwd: str = "/workspace"
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = Field(default=None, ge=1)
    output_limit_bytes: int | None = Field(default=None, ge=1024)


class SandboxExecutionResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    session_id: str | None = None
    container_id: str | None = None


class SandboxMergeResult(BaseModel):
    status: str
    changed_files: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)
