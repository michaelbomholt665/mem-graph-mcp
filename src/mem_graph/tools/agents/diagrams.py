#!/usr/bin/env python3
# src/mem_graph/tools/agents/diagrams.py
"""
MCP tool surface for the diagram agent.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastmcp import FastMCP
from ..markers import tier_2_tool
from pydantic import Field

from ...app.registry import AgentEntry, register_agent
from ...agents.map.diagram_agent import DiagramRequest, DiagramType, run_diagram_agent

mcp = FastMCP("diagrams", instructions="Tools for generating diagrams via mermaid.")
logger = logging.getLogger(__name__)

register_agent(
    AgentEntry(
        name="Diagram Agent",
        tool_name="generate_diagram",
        description="Generates and validates Mermaid system diagrams.",
        namespace="work",
        categories=["architecture", "documentation"],
        task_types=["diagramming", "visualization"],
    )
)


@tier_2_tool
@mcp.tool(tags={"namespace:work"})
async def generate_diagram(
    description: Annotated[str, Field(description="What to diagram — feature, system, flow, or relationship.")],
    diagram_type: Annotated[str | None, Field(description="Optional explicit diagram type (e.g. flowchart, sequence, state, er, class, architecture). Leave empty to infer.")] = None,
    context: Annotated[str, Field(description="Additional domain context or architecture notes if applicable.")] = "",
    style_hints: Annotated[list[str], Field(description="Optional style preferences (e.g. 'left to right', 'colorful').")] = [],
) -> dict:
    """Generate a Mermaid diagram from a description."""
    dtype = None
    if diagram_type:
        try:
            dtype = DiagramType(diagram_type.lower())
        except ValueError:
            logger.warning("Invalid diagram type '%s': Agent will infer type.", diagram_type)

    req = DiagramRequest(
        description=description,
        diagram_type=dtype,
        context=context,
        style_hints=style_hints,
    )

    try:
        output = await run_diagram_agent(req)
        return {
            "status": "completed",
            "mermaid_source": output.mermaid_source,
            "title": output.title,
            "description": output.description,
            "iterations_required": output.iterations,
            "inferred_type": output.diagram_type.value,
            "warnings": output.warnings,
        }
    except Exception as exc:
        logger.error("Diagram generation failed: %s", exc)
        return {"error": f"Agent graph execution failed: {str(exc)}"}
