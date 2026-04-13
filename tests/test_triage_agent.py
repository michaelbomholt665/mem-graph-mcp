#!/usr/bin/env python3
# tests/test_triage_agent.py
import os
os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest
from typing import cast
from pydantic_ai.tools import RunContext
from pydantic_ai.models.test import TestModel
from mem_graph.agents.document.triage_agent import triage_agent, TriageDependencies, process_batch, TriagedViolation, RawFinding, TriageDecision


class MockContext:
    def __init__(self, deps):
        self.deps = deps


@pytest.mark.asyncio
async def test_triage_agent_dependency_injection():
    model = TestModel(call_tools=[])
    deps = TriageDependencies(
        project_id="test",
    )

    with triage_agent.override(model=model):
        await triage_agent.run("Triage", deps=deps)


@pytest.mark.asyncio
async def test_triage_process_batch():
    f1 = RawFinding(rule_id="R1", file_path="f1.go", description="Desc")
    deps = TriageDependencies(project_id="test", raw_findings=[f1], existing_violations=[])
    ctx = cast(RunContext[TriageDependencies], MockContext(deps))
    
    # Fetch batch
    res = await process_batch(ctx, [0], [])
    assert "R1" in res
    assert "No existing matches." in res
    
    # Submit decision
    v1 = TriagedViolation(
        raw=f1,
        decision=TriageDecision.NEW,
        assessed_severity="minor",
        rationale="Valid new issue"
    )
    
    res2 = await process_batch(ctx, [], [v1])
    assert res2 == "No findings requested. Decisions stored."
    
    from mem_graph.agents.document.triage_agent import _get_state
    state = _get_state(ctx)
    assert len(state) == 1
    assert state[0].decision == TriageDecision.NEW
