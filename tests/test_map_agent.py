import os
os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest
from typing import cast
from pydantic_ai.tools import RunContext
from pydantic_ai.models.test import TestModel
from mem_graph.agents.map_agent import map_agent, MapDependencies, process_batch, FeatureLocation, FileRelationship


class MockContext:
    def __init__(self, deps):
        self.deps = deps


@pytest.mark.asyncio
async def test_map_agent_dependency_injection():
    model = TestModel(call_tools=[])
    deps = MapDependencies(
        package_path="/path/to/pkg",
        skills_content="Custom Skills",
    )

    with map_agent.override(model=model):
        await map_agent.run("Map", deps=deps)


@pytest.mark.asyncio
async def test_map_process_batch():
    deps = MapDependencies(package_path="/test")
    ctx = cast(RunContext[MapDependencies], MockContext(deps))
    
    # Empty batch
    res = await process_batch(ctx, [], [], [])
    assert res == "No files requested. Findings stored."
    
    from mem_graph.agents.map_agent import _get_state
    state = _get_state(ctx)
    assert len(state["features"]) == 0
    assert len(state["relationships"]) == 0

    # Submit features
    f1 = FeatureLocation(feature_name="A", primary_file="a.go", description="A feature")
    r1 = FileRelationship(source_file="a.go", target_file="b.go", relationship_kind="calls")
    
    res2 = await process_batch(ctx, [], [f1], [r1])
    assert res2 == "No files requested. Findings stored."
    
    state2 = _get_state(ctx)
    assert len(state2["features"]) == 1
    assert len(state2["relationships"]) == 1
    assert state2["features"][0].feature_name == "A"
