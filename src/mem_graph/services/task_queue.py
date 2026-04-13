"""Bounded in-memory queue for task-style tool execution.

This queue is used for non-SEP-1686 clients that call heavy tools directly.
The tools still advertise ``task=True`` so FastMCP task-aware clients can run
them through Docket, but ordinary callers get an immediate task identifier and
can poll via ``get_task_status``.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol

from ..models.task import Task, TaskProgress, TaskResult, TaskStatus


class ProgressReporter(Protocol):
    async def update(
        self,
        current: int,
        total: int,
        current_step: str,
        status_text: str,
    ) -> None: ...


TaskRunner = Callable[[ProgressReporter], Awaitable[Any]]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_progress_message(current_step: str, status_text: str) -> str:
    step = current_step.strip() or "working"
    detail = status_text.strip() or "Working."
    return f"{step}: {detail}"


class _QueueProgressReporter:
    def __init__(self, queue: TaskQueue, task_id: str) -> None:
        self._queue = queue
        self._task_id = task_id

    async def update(
        self,
        current: int,
        total: int,
        current_step: str,
        status_text: str,
    ) -> None:
        self._queue.update_progress(self._task_id, current, total, current_step, status_text)
        await asyncio.sleep(0)


class TaskQueue:
    def __init__(self, max_concurrent: int = 2, max_completed: int = 100):
        self.max_concurrent = max_concurrent
        self.max_completed = max_completed
        self.queue: deque[str] = deque()
        self.running: dict[str, Task] = {}
        self.completed: dict[str, Task] = {}
        self._tasks: dict[str, Task] = {}
        self._runners: dict[str, TaskRunner] = {}
        self._handles: dict[str, asyncio.Task[None]] = {}
        self._completed_order: deque[str] = deque()
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        """Initialize queue lifecycle hooks."""

    async def shutdown(self) -> dict[str, int]:
        """Cancel unfinished tasks because queue state is in-memory only."""

        async with self._lock:
            queued_ids = list(self.queue)
            running_handles = list(self._handles.values())
            self.queue.clear()

            for task_id in queued_ids:
                task = self._tasks.get(task_id)
                if task is None:
                    continue
                task.status = TaskStatus.CANCELLED
                task.completed_at = _utc_now()
                task.progress = TaskProgress(
                    current=100,
                    total=100,
                    percentage=100.0,
                    current_step="cancelled",
                    status_text="Task cancelled during server shutdown.",
                    message=_format_progress_message(
                        "cancelled",
                        "Task cancelled during server shutdown.",
                    ),
                )
                self._remember_completed(task_id)

            for handle in running_handles:
                handle.cancel()

        if running_handles:
            await asyncio.gather(*running_handles, return_exceptions=True)

        return {
            "queued_cancelled": len(queued_ids),
            "running_cancelled": len(running_handles),
        }

    async def enqueue(
        self,
        tool_name: str,
        runner: TaskRunner,
        arguments: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Task:
        task = Task(tool_name=tool_name, arguments=arguments or {}, session_id=session_id)
        self._tasks[task.task_id] = task
        self._runners[task.task_id] = runner

        self.update_progress(
            task.task_id,
            current=0,
            total=100,
            current_step="queued",
            status_text="Task accepted and waiting for execution.",
        )

        async with self._lock:
            self.queue.append(task.task_id)
            self._drain_locked()

        return task.model_copy(deep=True)

    def update_progress(
        self,
        task_id: str,
        current: int,
        total: int,
        current_step: str,
        status_text: str,
    ) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return

        total_value = max(total, 1)
        bounded_current = max(0, min(current, total_value))
        percentage = round((bounded_current / total_value) * 100, 2)
        task.progress = TaskProgress(
            current=bounded_current,
            total=total_value,
            percentage=percentage,
            current_step=current_step,
            status_text=status_text,
            message=_format_progress_message(current_step, status_text),
        )

    def _drain_locked(self) -> None:
        while self.queue and len(self._handles) < self.max_concurrent:
            task_id = self.queue.popleft()
            task = self._tasks.get(task_id)
            if task is None or task.status == TaskStatus.CANCELLED:
                continue

            task.status = TaskStatus.RUNNING
            task.started_at = _utc_now()
            self.update_progress(
                task_id,
                current=1,
                total=max(task.progress.total, 100),
                current_step="running",
                status_text="Task execution started.",
            )
            self.running[task_id] = task
            self._handles[task_id] = asyncio.create_task(
                self._run_task(task_id),
                name=f"mem-graph-{task.tool_name}-{task_id}",
            )

    async def _run_task(self, task_id: str) -> None:
        task = self._tasks[task_id]
        runner = self._runners[task_id]
        reporter = _QueueProgressReporter(self, task_id)

        try:
            result = await runner(reporter)
            if task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.COMPLETED
                task.result = TaskResult(data=result)
                self.update_progress(
                    task_id,
                    current=100,
                    total=100,
                    current_step="completed",
                    status_text="Task completed successfully.",
                )
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.cancellation_requested = False
            self.update_progress(
                task_id,
                current=100,
                total=100,
                current_step="cancelled",
                status_text="Task cancelled.",
            )
            raise
        except Exception as exc:  # noqa: BLE001
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.result = TaskResult(errors=[str(exc)])
            self.update_progress(
                task_id,
                current=max(task.progress.current, 1),
                total=max(task.progress.total, 100),
                current_step="failed",
                status_text=f"Task failed: {exc}",
            )
        finally:
            task.completed_at = _utc_now()
            async with self._lock:
                self.running.pop(task_id, None)
                self._handles.pop(task_id, None)
                self._runners.pop(task_id, None)
                self._remember_completed(task_id)
                self._drain_locked()

    def _remember_completed(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return

        self.completed[task_id] = task
        self._completed_order.append(task_id)

        while len(self._completed_order) > self.max_completed:
            stale_id = self._completed_order.popleft()
            self.completed.pop(stale_id, None)
            self._tasks.pop(stale_id, None)

    def get_task(self, task_id: str) -> Task | None:
        task = self._tasks.get(task_id)
        return task.model_copy(deep=True) if task is not None else None

    async def cancel_task(self, task_id: str) -> Task | None:
        async with self._lock:
            if task_id in self.queue:
                self.queue.remove(task_id)
                task = self._tasks.get(task_id)
                if task is None:
                    return None
                task.status = TaskStatus.CANCELLED
                task.completed_at = _utc_now()
                self.update_progress(
                    task_id,
                    current=100,
                    total=100,
                    current_step="cancelled",
                    status_text="Task cancelled before execution started.",
                )
                self._runners.pop(task_id, None)
                self._remember_completed(task_id)
                return task.model_copy(deep=True)

            handle = self._handles.get(task_id)
            task = self._tasks.get(task_id)
            if handle is None or task is None:
                return self.get_task(task_id)

            task.cancellation_requested = True
            self.update_progress(
                task_id,
                current=max(task.progress.current, 1),
                total=max(task.progress.total, 100),
                current_step="cancelling",
                status_text="Cancellation requested.",
            )
            handle.cancel()

        await asyncio.gather(handle, return_exceptions=True)
        return self.get_task(task_id)


task_queue = TaskQueue(max_concurrent=2)
