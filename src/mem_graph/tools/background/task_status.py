from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from ..markers import tier_2_tool
from fastmcp.server.context import Context
from pydantic import Field

from ...models.task import Task
from ...services.task_queue import task_queue

mcp = FastMCP("background", instructions="Background task status and cancellation tools.")


def build_task_submission(task: Task) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "tool": task.tool_name,
        "status": task.status.value,
        "progress": task.progress.model_dump(),
        "poll_with": "get_task_status",
        "cancel_with": "cancel_task",
        "message": "Background task accepted. Poll for status updates.",
    }


def build_task_status(task: Task) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task_id": task.task_id,
        "tool": task.tool_name,
        "status": task.status.value,
        "progress": task.progress.model_dump(),
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "cancellation_requested": task.cancellation_requested,
    }

    if task.result is not None:
        payload["result"] = task.result.data
        if task.result.errors:
            payload["errors"] = task.result.errors

    if task.error is not None:
        payload["error"] = task.error

    return payload


def _can_access(task: Task, ctx: Context | None) -> bool:
    if ctx is None or task.session_id is None:
        return True
    return ctx.session_id == task.session_id


@tier_2_tool
@mcp.tool(tags={"namespace:background"})
async def get_task_status(
    task_id: str = Field(description="Task identifier returned by a background tool."),
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Return the current status, progress, and result data for an in-memory background task."""
    task = task_queue.get_task(task_id)
    if task is None or not _can_access(task, ctx):
        return {"error": f"Task {task_id!r} not found."}
    return build_task_status(task)


@tier_2_tool
@mcp.tool(tags={"namespace:background"})
async def cancel_task(
    task_id: str = Field(description="Task identifier returned by a background tool."),
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Cancel a queued or running in-memory background task."""
    existing = task_queue.get_task(task_id)
    if existing is None or not _can_access(existing, ctx):
        return {"error": f"Task {task_id!r} not found."}

    task = await task_queue.cancel_task(task_id)
    if task is None:
        return {"error": f"Task {task_id!r} not found."}

    response = build_task_status(task)
    response["cancelled"] = task.status.value == "cancelled"
    return response