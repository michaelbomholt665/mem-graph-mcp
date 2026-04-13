import os
os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest
from typing import cast
from pydantic_ai.tools import RunContext
from pydantic_ai.models.test import TestModel
from mem_graph.agents.decision_agent import decision_agent, DecisionDependencies, process_batch, DecisionReview, DriftStatus


class MockContext:
    def __init__(self, deps):
        self.deps = deps


@pytest.mark.asyncio
async def test_decision_agent_dependency_injection():
    model = TestModel(call_tools=[])
    deps = DecisionDependencies(
        package_path="/path/to/pkg",
        project_id="test",
    )

    with decision_agent.override(model=model):
        await decision_agent.run("Review", deps=deps)


@pytest.mark.asyncio
async def test_decision_process_batch():
    deps = DecisionDependencies(package_path="/test", project_id="test")
    ctx = cast(RunContext[DecisionDependencies], MockContext(deps))
    
    # Submit review
    r1 = DecisionReview(
        decision_id="D1",
        decision_title="Test Decision",
        status=DriftStatus.HONOURED,
        evidence="Found evidence",
        recommendation="None"
    )
    
    res = await process_batch(ctx, [], [r1])
    assert res == "No files requested. Reviews stored."
    
    from mem_graph.agents.decision_agent import _get_state
    state = _get_state(ctx)
    assert len(state) == 1
    assert state[0].decision_id == "D1"
