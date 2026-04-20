# Design: Phase 4b - Polish (Background Tasks)

**Status:** Design Phase  
**Priority:** Medium (Performance feature)  
**Date:** 2026-04-13

---

## Overview

Phase 4b moves heavy operations (audits, mapping, orchestration) to background tasks. Instead of blocking the client during long runs, tools return a task ID immediately and clients poll for progress.

FastMCP's `task=True` parameter enables this pattern: the server runs the operation asynchronously while the client monitors progress.

---

## Goals

1. **Prevent Timeout:** Long operations don't block client connection
2. **Responsive UX:** Client gets immediate feedback (task ID)
3. **Progress Visibility:** Clients can poll or stream progress updates
4. **Cancellation:** Users can cancel long-running tasks

---

## Scope

### In Scope
- Mark heavy tools with `task=True` (audit, map, orchestrate)
- Implement async execution with progress tracking
- Create task queue for managing concurrent operations
- Implement task status API (status, progress, results)
- Add cancellation support

### Out of Scope
- Persistent task storage (tasks live in memory during server uptime)
- Long-term task history (use graph audit log instead)
- Complex scheduler (simple queue is sufficient)

---

## Architecture

### 1. Task Model

```python
# src/mem_graph/models/task.py

from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import uuid4

class TaskStatus(str, Enum):
    """Status of a background task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskProgress(BaseModel):
    """Progress info for a task."""
    current: int = Field(description="Current progress value")
    total: int = Field(description="Total progress target")
    percentage: float = Field(description="Progress as fraction 0-1")
    message: str = Field(default="", description="Current status message")

class TaskResult(BaseModel):
    """Result of a completed task."""
    data: dict = Field(description="Task output")
    errors: list[str] = Field(default_factory=list, description="Warnings/errors")

class Task(BaseModel):
    """A background task being executed."""
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    tool_name: str = Field(description="Which tool this task runs")
    arguments: dict = Field(description="Arguments passed to tool")
    status: TaskStatus = TaskStatus.PENDING
    
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    progress: TaskProgress = Field(default_factory=lambda: TaskProgress(current=0, total=0, percentage=0.0))
    result: TaskResult | None = None
    error: str | None = None
```

### 2. Task Queue

```python
# src/mem_graph/services/task_queue.py

import asyncio
from collections import deque
from typing import Callable, Any

class TaskQueue:
    """Simple queue for background tasks."""
    
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.queue: deque[Task] = deque()
        self.running: dict[str, Task] = {}
        self.completed: dict[str, Task] = {}
    
    async def enqueue(
        self,
        tool_name: str,
        arguments: dict,
        func: Callable[..., Any],
    ) -> Task:
        """Create and enqueue a task."""
        
        task = Task(
            tool_name=tool_name,
            arguments=arguments,
        )
        
        # Store executable function
        task._func = func
        self.queue.append(task)
        
        # Try to start immediately
        asyncio.create_task(self._process_queue())
        
        return task
    
    async def _process_queue(self) -> None:
        """Process queued tasks, respecting concurrency limit."""
        
        while self.queue and len(self.running) < self.max_concurrent:
            task = self.queue.popleft()
            self.running[task.task_id] = task
            
            # Run task in background
            asyncio.create_task(self._run_task(task))
    
    async def _run_task(self, task: Task) -> None:
        """Execute a single task."""
        
        try:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            
            # Run the function (it will call ctx.report_progress)
            result = await task._func(**task.arguments)
            
            task.result = TaskResult(data=result)
            task.status = TaskStatus.COMPLETED
            
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
        
        finally:
            task.completed_at = datetime.now()
            
            # Move to completed
            del self.running[task.task_id]
            self.completed[task.task_id] = task
            
            # Process next queued task
            await self._process_queue()
    
    def get_task(self, task_id: str) -> Task | None:
        """Get task by ID (running, completed, or queued)."""
        
        return (
            self.running.get(task_id) or
            self.completed.get(task_id) or
            next((t for t in self.queue if t.task_id == task_id), None)
        )
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a queued or running task."""
        
        # If queued, remove from queue
        self.queue = deque(t for t in self.queue if t.task_id != task_id)
        
        # If running, it will be cancelled by cancellation token (future work)
        # For now, we can only cancel queued tasks
        
        return True

# Global task queue
task_queue = TaskQueue(max_concurrent=3)
```

### 3. Heavy Tools Marked as Tasks

```python
# src/mem_graph/tools/agents/audit.py

from fastmcp.server.context import Context
from ..services.task_queue import task_queue

@mcp.tool(task=True)  # Mark as background task
async def audit_package(
    ctx: Context,
    package_path: str,
    severity: str = "all",
) -> dict:
    """
    Audit a package (runs as background task).
    
    Returns immediately with task_id.
    Client polls get_task_status for progress.
    """
    
    # Create task
    async def run_audit() -> dict:
        findings = []
        files = await enumerate_files(package_path)
        
        for i, file_path in enumerate(files):
            # Process file
            result = await audit_file(file_path)
            findings.extend(result)
            
            # Report progress
            await ctx.report_progress(
                progress=(i + 1) / len(files),
                message=f"Auditing {file_path}",
            )
        
        return {
            "total_findings": len(findings),
            "findings": findings,
        }
    
    # Enqueue and return task ID immediately
    task = await task_queue.enqueue(
        tool_name="audit_package",
        arguments={"package_path": package_path, "severity": severity},
        func=run_audit,
    )
    
    return {"task_id": task.task_id, "status": task.status}

@mcp.tool()
async def get_task_status(task_id: str) -> dict:
    """Get status of a background task."""
    
    task = task_queue.get_task(task_id)
    
    if not task:
        return {"error": f"Task {task_id} not found"}
    
    response = {
        "task_id": task.task_id,
        "tool": task.tool_name,
        "status": task.status,
        "progress": {
            "current": task.progress.current,
            "total": task.progress.total,
            "percentage": task.progress.percentage,
            "message": task.progress.message,
        },
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }
    
    if task.status == TaskStatus.COMPLETED and task.result:
        response["result"] = task.result.data
    
    if task.status == TaskStatus.FAILED:
        response["error"] = task.error
    
    return response

@mcp.tool()
async def cancel_task(task_id: str) -> dict:
    """Cancel a running or queued task."""
    
    success = await task_queue.cancel_task(task_id)
    
    task = task_queue.get_task(task_id)
    
    return {
        "task_id": task_id,
        "cancelled": success,
        "status": task.status if task else "not_found",
    }
```

### 4. Client Polling Pattern

Clients poll for task progress:

```python
# Pseudo-code for MCP client

async def audit_and_wait(package_path: str) -> dict:
    """Call audit_package and wait for completion."""
    
    # Start audit (returns immediately)
    result = await client.call_tool("audit_package", {"package_path": package_path})
    task_id = result["task_id"]
    
    # Poll until complete
    while True:
        status = await client.call_tool("get_task_status", {"task_id": task_id})
        
        # Print progress
        progress = status["progress"]["percentage"]
        message = status["progress"]["message"]
        print(f"[{progress*100:.0f}%] {message}")
        
        if status["status"] in ["completed", "failed", "cancelled"]:
            break
        
        # Wait before next poll
        await asyncio.sleep(1)
    
    # Return final result
    if status["status"] == "completed":
        return status["result"]
    else:
        raise Exception(f"Task {status['status']}: {status.get('error')}")
```

### 5. Server Configuration

```python
# src/mem_graph/server.py

from .services.task_queue import task_queue

# On server startup
@mcp.lifespan()
async def server_lifespan():
    # Initialize task queue
    # (could load persisted tasks from DB if desired)
    
    yield
    
    # On shutdown
    # Optionally cancel running tasks or persist them
    pass

# Expose task queue to context
@mcp.middleware
async def inject_task_queue(context: MiddlewareContext, call_next: CallNext):
    context.task_queue = task_queue
    return await call_next()
```

---

## Benefits

1. **No Timeouts:** Long operations don't block client
2. **Progress Visibility:** Clients see real-time updates
3. **Responsive:** Immediate feedback while work continues
4. **Cancellation:** Users can stop long operations
5. **Simple:** No complex persistence needed

---

## Which Tools to Mark as Tasks

| Tool | Async? | Rationale |
|------|--------|-----------|
| `audit_package` | YES | Can take minutes on large codebases |
| `map_codebase` | YES | Traverses entire tree |
| `orchestrate_codebase` | YES | Multiple agent passes + refinement |
| `triage_violations` | YES | Large violation sets |
| `memory_store` | NO | Typically sub-second |
| `memory_recall` | NO | Query is fast (with indexes) |
| `execute_fix` | YES | May involve multiple file edits |

---

## Implementation Checklist

- [ ] Create `Task` and `TaskProgress` models
- [ ] Implement `TaskQueue` class
- [ ] Add `@mcp.tool(task=True)` to heavy tools
- [ ] Implement async execution in tools
- [ ] Create `get_task_status` tool
- [ ] Create `cancel_task` tool
- [ ] Implement `ctx.report_progress()` calls in tools
- [ ] Test task execution in MCP inspector
- [ ] Test progress reporting
- [ ] Test cancellation

---

## Success Criteria

1. Heavy tools return task ID immediately
2. Clients can poll for progress
3. Tasks execute in order (respecting concurrency limit)
4. Progress updates are visible
5. Cancellation works
6. No regression in accuracy/results

---

## Dependencies

- FastMCP with `task=True` support
- `asyncio` for task execution
- Pydantic for `Task`/`TaskProgress` models

---

## Future Enhancements

1. **Persistent Tasks:** Store task state in DB for server restarts
2. **WebSocket Progress:** Stream progress instead of polling
3. **Priority Queue:** Allow high-priority tasks to jump queue
4. **Task Limits:** Prevent runaway task accumulation
5. **Rate Limiting:** Don't allow unlimited concurrent tasks from single client
