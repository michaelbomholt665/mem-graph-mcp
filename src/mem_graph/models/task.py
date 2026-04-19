from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from ..ids import id_generate_v7


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BackgroundTaskStatus(str, Enum):
    """Lifecycle states for in-process background tasks."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Backwards-compatible alias so existing code importing TaskStatus still works.
TaskStatus = BackgroundTaskStatus


class TaskProgress(BaseModel):
    """Normalized progress payload exposed by the status API."""

    current: int = Field(default=0, ge=0)
    total: int = Field(default=100, ge=1)
    percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    current_step: str = Field(default="queued")
    status_text: str = Field(default="Task accepted and waiting for execution.")
    message: str = Field(default="queued: Task accepted and waiting for execution.")


class TaskResult(BaseModel):
    """Structured result payload for completed tasks."""

    data: Any | None = None
    errors: list[str] = Field(default_factory=list)


class Task(BaseModel):
    """Task metadata stored in the in-memory task queue."""

    task_id: str = Field(default_factory=id_generate_v7)
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    status: BackgroundTaskStatus = BackgroundTaskStatus.QUEUED
    created_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: TaskProgress = Field(default_factory=TaskProgress)
    result: TaskResult | None = None
    error: str | None = None
    cancellation_requested: bool = False
