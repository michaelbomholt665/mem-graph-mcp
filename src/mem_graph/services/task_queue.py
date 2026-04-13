"""
Simple in-memory TaskQueue for background execution of long-running tools.

This is a conservative, dependency-free shim useful for local development and
testing. It can be replaced by native FastMCP `task=True` behavior when
`docs/planning/tasks/007-fastmcp-task.md` is implemented.
"""
from __future__ import annotations

import asyncio
import inspect
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Optional
import uuid


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    task_id: str
    tool_name: str
    arguments: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    progress: Dict[str, Any] = field(default_factory=lambda: {"current": 0, "total": 0, "message": ""})
    _func: Optional[Callable[..., Any]] = None


class TaskQueue:
    def __init__(self, max_concurrent: int = 2):
        self.max_concurrent = max_concurrent
        self.queue: deque[Task] = deque()
        self.running: Dict[str, Task] = {}
        self.completed: Dict[str, Task] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, tool_name: str, func: Callable[..., Any], arguments: Dict[str, Any] | None = None) -> Task:
        task_id = uuid.uuid4().hex
        task = Task(task_id=task_id, tool_name=tool_name, arguments=arguments or {}, _func=func)
        self.queue.append(task)
        # schedule processing
        await self._process_queue()
        return task

    async def _process_queue(self) -> None:
        async with self._lock:
            while self.queue and len(self.running) < self.max_concurrent:
                task = self.queue.popleft()
                self.running[task.task_id] = task
                asyncio.create_task(self._run_task(task))

    async def _run_task(self, task: Task) -> None:
        try:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            func = task._func
            if func is not None and inspect.iscoroutinefunction(func):
                result = await func(**task.arguments)
            elif func is not None:
                # run in thread if sync function
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, lambda: func(**task.arguments))
            else:
                raise RuntimeError("Task function is None")

            task.result = result
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
        finally:
            task.completed_at = datetime.now(timezone.utc)
            # move to completed
            self.running.pop(task.task_id, None)
            self.completed[task.task_id] = task
            # try to schedule more
            await self._process_queue()

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.running.get(task_id) or self.completed.get(task_id) or next((t for t in self.queue if t.task_id == task_id), None)

    def cancel_task(self, task_id: str) -> bool:
        # remove from queue if present
        for t in self.queue:
            if t.task_id == task_id:
                self.queue.remove(t)
                t.status = TaskStatus.CANCELLED
                self.completed[t.task_id] = t
                return True
        # cannot reliably cancel running tasks here
        running = self.running.get(task_id)
        if running:
            # mark as cancelled; worker may still finish
            running.status = TaskStatus.CANCELLED
            return True
        return False


# global instance for simple import
task_queue = TaskQueue(max_concurrent=2)
