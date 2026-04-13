#!/usr/bin/env python3
# tests/test_audit.py
import os
os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest
from typing import cast
from pydantic_ai.tools import RunContext
from pydantic_ai.models.test import TestModel
from mem_graph.agents.audit.audit_agent import audit_agent, AuditDependencies, process_batch, FileAuditResult


class MockContext:
    def __init__(self, deps):
        self.deps = deps


@pytest.mark.asyncio
async def test_audit_agent_dependency_injection():
    model = TestModel(call_tools=[])
    deps = AuditDependencies(
        package_path="/path/to/pkg",
        skills_content="Custom Skills",
    )

    with audit_agent.override(model=model):
        await audit_agent.run("Audit", deps=deps)


@pytest.mark.asyncio
async def test_audit_process_batch():
    deps = AuditDependencies(package_path="/test")
    ctx = cast(RunContext[AuditDependencies], MockContext(deps))
    
    # State should be initialized
    from mem_graph.agents.audit.audit_agent import _get_state
    
    # Mock file reading by just providing non-existent paths, we expect ERROR:NOT_FOUND
    res = await process_batch(ctx, ["invalid.go", "also_invalid.go"], [])
    assert "ERROR:NOT_FOUND" in res
    
    state = _get_state(ctx)
    assert len(state) == 0

    # Submit a finding
    finding = FileAuditResult(file_path="old.go", findings=[], skipped=False)
    res2 = await process_batch(ctx, [], [finding])
    
    assert res2 == "No files requested. Findings stored."
    
    state2 = _get_state(ctx)
    assert len(state2) == 1
    assert state2[0].file_path == "old.go"
