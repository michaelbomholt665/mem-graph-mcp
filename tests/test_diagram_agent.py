#!/usr/bin/env python3
# tests/test_diagram_agent.py
import os
os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest
from pydantic_ai.models.test import TestModel

from mem_graph.agents.map.diagram_agent import (
    _classifier_agent,
    _describer_agent,
    _generator_agent,
    DiagramType,
    DiagramRequest,
    run_diagram_agent,
    _validate_mermaid,
)

@pytest.mark.asyncio
async def test_diagram_agent_graph_wiring():
    req = DiagramRequest(
        description="A simple flowchart of login system.",
    )

    classifier_model = TestModel()
    generator_model = TestModel(custom_output_text="```mermaid\nflowchart TD\nA-->B\n```")
    describer_model = TestModel(custom_output_text="A flowchart.")

    # Override the sub-agents so that the entire pydantic-graph executes logically.
    with _classifier_agent.override(model=classifier_model):
        with _generator_agent.override(model=generator_model):
            with _describer_agent.override(model=describer_model):
                output = await run_diagram_agent(req)

    assert output.diagram_type == DiagramType.FLOWCHART
    assert "flowchart TD" in output.mermaid_source
    assert output.iterations <= 3
    assert output.description == "A flowchart."


def test_validate_mermaid_struct():
    # Valid
    errors = _validate_mermaid("flowchart TD\nA-->B", DiagramType.FLOWCHART)
    assert not errors

    # Invalid header
    errors = _validate_mermaid("graph LR\nA-->B", DiagramType.SEQUENCE)
    assert len(errors) == 1
    assert "does not match expected headers" in errors[0]

    # Unbalanced syntax
    errors = _validate_mermaid("flowchart TD\nA{-->B", DiagramType.FLOWCHART)
    assert any("Unbalanced" in e for e in errors)
