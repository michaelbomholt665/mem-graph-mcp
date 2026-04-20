from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from ..ids import id_generate_v7
from .agent_outputs import JSONValue


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

    current: int = Field(
        default=0,
        ge=0,
        description="Current completed work-unit count for the task.",
    )
    total: int = Field(
        default=100,
        ge=1,
        description="Total work-unit count used to compute percentage progress.",
    )
    percentage: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Precomputed percentage representation of current over total.",
    )
    current_step: str = Field(
        default="queued",
        description="Short machine-readable step label describing the current stage.",
    )
    status_text: str = Field(
        default="Task accepted and waiting for execution.",
        description="Human-readable status summary suitable for dashboards or APIs.",
    )
    message: str = Field(
        default="queued: Task accepted and waiting for execution.",
        description="Verbose status message that includes state plus any operator-facing detail.",
    )


class TaskResult(BaseModel):
    """Structured result payload for completed tasks."""

    data: JSONValue | None = Field(
        default=None,
        description="JSON-safe result payload returned by the completed background task.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Any error messages captured while producing the result payload.",
    )


class Task(BaseModel):
    """Task metadata stored in the in-memory task queue."""

    task_id: str = Field(
        default_factory=id_generate_v7,
        description="Stable identifier assigned when the task enters the in-memory queue.",
    )
    tool_name: str = Field(
        description="Tool name or workflow identifier responsible for executing this task.",
    )
    arguments: dict[str, JSONValue] = Field(
        default_factory=dict,
        description="JSON-safe argument payload captured when the task was enqueued.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session identifier used to associate the task with a client session.",
    )
    status: BackgroundTaskStatus = Field(
        default=BackgroundTaskStatus.QUEUED,
        description="Current lifecycle state for the background task.",
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when the task was accepted into the queue.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when execution actually started.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when execution finished, failed, or was cancelled.",
    )
    progress: TaskProgress = Field(
        default_factory=TaskProgress,
        description="Normalized progress snapshot returned by the task status API.",
    )
    result: TaskResult | None = Field(
        default=None,
        description="Structured result payload recorded after successful completion.",
    )
    error: str | None = Field(
        default=None,
        description="Top-level task failure message when execution did not complete successfully.",
    )
    cancellation_requested: bool = Field(
        default=False,
        description="True when a client requested cancellation before the task finished.",
    )
