#!/usr/bin/env python3
# src/mem_graph/tools/agents/map.py
"""
MCP tool surface for the map agent.

Exposes a tool for mapping the architecture and feature geography of a codebase.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

import anyio
from fastmcp import FastMCP
from pydantic import Field

from ...agents.map_agent import MapDependencies, map_agent

mcp = FastMCP("map", instructions="Codebase cartography mapping tools.")
logger = logging.getLogger(__name__)

_SKILLS_PATH = os.path.join(os.getcwd(), "skills", "map_agent", "SKILL.md")


async def _load_skills() -> str:
    if not os.path.exists(_SKILLS_PATH):
        return ""
    try:
        async with await anyio.open_file(_SKILLS_PATH, "r", encoding="utf-8") as f:
            return await f.read()
    except Exception as exc:
        logger.warning("Failed to load skills from %s: %s", _SKILLS_PATH, exc)
        return ""


@mcp.tool(tags={"namespace:audit"})
async def map_codebase(
    package_path: Annotated[
        str,
        Field(description="Absolute path to the package directory to map"),
    ],
    known_features: Annotated[
        list[str],
        Field(description="List of optionally known subsystems"),
    ] = [],
    file_extension: Annotated[
        str,
        Field(description="Source file extension to analyse. Defaults to '.py'."),
    ] = ".py",
) -> dict:
    """
    Map and discover the feature geography, architecture, and knowledge relationships of a codebase.

    Produces a summary of what features exist, where they are implemented natively,
    and what files they depend on or are consumed by. Returns entry points and relationship counts.
    """
    if not os.path.exists(package_path):
        return {"error": f"Package path not found: {package_path}"}

    skills_content = await _load_skills()
    deps = MapDependencies(
        package_path=package_path,
        file_extension=file_extension,
        known_features=list(known_features),
        skills_content=skills_content,
    )

    try:
        async with map_agent.run_stream(
            "Begin mapping. Call list_files, read them in batches using process_batch, and map features/relationships to finalize.",
            deps=deps,
        ) as result:
            report = await result.get_output()
    except Exception as exc:
        logger.error("Map agent execution failed: %s", exc)
        return {"error": f"Agent failed: {exc}"}

    return {
        "status": "completed" if not report.partial_failure else "partial",
        "summary": report.summary,
        "entry_points": report.entry_points,
        "features_mapped": len(report.features),
        "relationships_mapped": len(report.relationships),
    }
