#!/usr/bin/env python3
# tests/test_task_agent.py
import os
os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest
from typing import cast
from pydantic_ai.tools import RunContext
from pydantic_ai.models.test import TestModel
from mem_graph.agents.document.task_agent import task_agent, TaskDependencies, process_batch, Task


class MockContext:
    def __init__(self, deps):
        self.deps = deps


@pytest.mark.asyncio
async def test_task_agent_dependency_injection():
    model = TestModel(call_tools=[])
    deps = TaskDependencies(
        feature_description="Build a cache",
        project_id="test",
    )

    with task_agent.override(model=model):
        await task_agent.run("Task", deps=deps)


@pytest.mark.asyncio
async def test_task_process_batch():
    deps = TaskDependencies(feature_description="Build a cache", project_id="test")
    ctx = cast(RunContext[TaskDependencies], MockContext(deps))
    
    # Send a query
    res = await process_batch(ctx, ["Where is the cache?"], [])
    assert "Where is the cache?" in res
    assert "Context query stub" in res
    
    # Submit task
    t1 = Task(
        task_id="T1",
        title="Create cache",
        description="Creates cache",
        phase="planning",
    )
    
    res2 = await process_batch(ctx, [], [t1])
    assert res2 == "No context queries requested. Tasks stored."
    
    from mem_graph.agents.document.task_agent import _get_state
    state = _get_state(ctx)
    assert len(state) == 1
    assert state[0].task_id == "T1"
