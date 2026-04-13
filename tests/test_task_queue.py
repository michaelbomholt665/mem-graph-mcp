from __future__ import annotations

import asyncio

import pytest

from mem_graph.models.task import Task


async def _wait_for_status(queue, task_id: str, expected: str) -> Task:
    async def poll() -> Task:
        while True:
            task = queue.get_task(task_id)
            if task is not None and task.status.value == expected:
                return task
            await asyncio.sleep(0)

    return await asyncio.wait_for(poll(), timeout=2.0)


@pytest.mark.asyncio
async def test_task_queue_respects_order_and_concurrency(tmp_path):
    from mem_graph.services.task_queue import TaskQueue

    queue = TaskQueue(max_concurrent=1, max_completed=10)
    started_one = asyncio.Event()
    started_two = asyncio.Event()
    finish_one = asyncio.Event()
    finish_two = asyncio.Event()

    async def runner_one(reporter):
        await reporter.update(20, 100, "scan", "Scanning the first package.")
        started_one.set()
        await finish_one.wait()
        return {"worker": "one"}

    async def runner_two(reporter):
        await reporter.update(25, 100, "scan", "Scanning the second package.")
        started_two.set()
        await finish_two.wait()
        return {"worker": "two"}

    task_one = await queue.enqueue("audit_package", runner_one, {"package_path": str(tmp_path / "one")})
    task_two = await queue.enqueue("map_codebase", runner_two, {"package_path": str(tmp_path / "two")})

    await started_one.wait()
    queued_one = queue.get_task(task_one.task_id)
    queued_two = queue.get_task(task_two.task_id)
    assert queued_one is not None
    assert queued_two is not None
    assert queued_one.status.value == "running"
    assert queued_two.status.value == "queued"

    finish_one.set()
    await started_two.wait()
    completed_one = queue.get_task(task_one.task_id)
    running_two = queue.get_task(task_two.task_id)
    assert completed_one is not None
    assert running_two is not None
    assert completed_one.status.value == "completed"
    assert running_two.status.value == "running"

    finish_two.set()
    completed_two = await _wait_for_status(queue, task_two.task_id, "completed")
    result = completed_two.result
    assert result is not None
    assert result.data == {"worker": "two"}


@pytest.mark.asyncio
async def test_task_queue_cancels_queued_and_running_tasks(tmp_path):
    from mem_graph.services.task_queue import TaskQueue

    queue = TaskQueue(max_concurrent=1, max_completed=10)
    started = asyncio.Event()
    release = asyncio.Event()

    async def runner(reporter):
        await reporter.update(10, 100, "audit", "Running the audit worker.")
        started.set()
        await release.wait()
        return {"ok": True}

    running = await queue.enqueue("audit_package", runner, {"package_path": str(tmp_path / "live")})
    queued = await queue.enqueue("map_codebase", runner, {"package_path": str(tmp_path / "queued")})

    await started.wait()
    queued_after_cancel = await queue.cancel_task(queued.task_id)
    running_after_cancel = await queue.cancel_task(running.task_id)

    assert queued_after_cancel is not None
    assert queued_after_cancel.status.value == "cancelled"
    assert running_after_cancel is not None
    assert running_after_cancel.status.value == "cancelled"


@pytest.mark.asyncio
async def test_get_task_status_reports_terminal_results(monkeypatch):
    from mem_graph.services.task_queue import TaskQueue
    from mem_graph.tools.background import task_status as status_tools

    queue = TaskQueue(max_concurrent=1, max_completed=10)

    async def runner(reporter):
        await reporter.update(50, 100, "triage", "Halfway through triage.")
        return {"summary": "complete"}

    task = await queue.enqueue("triage_violations", runner, {"project_id": "P1"})
    await _wait_for_status(queue, task.task_id, "completed")
    monkeypatch.setattr(status_tools, "task_queue", queue)

    status = await status_tools.get_task_status(task.task_id)
    assert status["status"] == "completed"
    assert status["progress"]["current_step"] == "completed"
    assert status["result"] == {"summary": "complete"}