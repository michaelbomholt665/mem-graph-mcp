#!/usr/bin/env python3
# src/mem_graph/tools/agents/map.py
"""
MCP tool surface for the map agent.

Exposes a tool for mapping the architecture and feature geography of a codebase.

FastMCP 3.0 upgrades:
- ``ctx: Context`` injected for progress reporting and client logging.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

import anyio
from fastmcp import FastMCP
from ..markers import tier_2_tool
from fastmcp.server.context import Context
from mcp.types import Icon
from pydantic import Field

from ...app.registry import AgentEntry, register_agent
from ...agents.map.map_agent import MapDependencies, map_agent
from ...observability import traced_tool
from ...services.task_queue import task_queue
from ..background.progress import ContextProgressReporter, ProgressReporter, report_step
from ..background.task_status import build_task_submission

mcp = FastMCP("map", instructions="Codebase cartography mapping tools.")
logger = logging.getLogger(__name__)

register_agent(
    AgentEntry(
        name="Map Agent",
        tool_name="map_codebase",
        description="Maps feature geography and codebase relationships.",
        namespace="audit",
        categories=["code", "architecture"],
        task_types=["codebase_map", "feature_mapping", "relationship_mapping"],
    )
)

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


@tier_2_tool
@mcp.tool(
    tags={"namespace:audit"},
    icons=[Icon(src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0Ij48cGF0aCBkPSJNMTIgMkM2LjQ4IDIgMiA2LjQ4IDIgMTJzNC40OCAxMCAxMCAxMCAxMC00LjQ4IDEwLTEwUzE3LjUyIDIgMTIgMnptMCA4Yy0xLjEgMC0yLS45LTIgLTJzMi45IDIgMi4zNzZoLTJ6TTE4IDE2SDlWMTBoOXY2eiIvPjwvc3ZnPg==", mimeType="image/svg+xml")],
    task=True
)
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
    ctx: Context = None,  # type: ignore[assignment]
) -> dict:
    """Map features and relationships across a codebase."""
    if ctx is not None and ctx.is_background_task:
        reporter = ContextProgressReporter(ctx)
        return await _map_codebase_worker(
            package_path=package_path,
            known_features=list(known_features),
            file_extension=file_extension,
            reporter=reporter,
        )

    task = await task_queue.enqueue(
        tool_name="map_codebase",
        arguments={
            "package_path": package_path,
            "known_features": list(known_features),
            "file_extension": file_extension,
        },
        session_id=ctx.session_id if ctx is not None else None,
        runner=lambda reporter: _map_codebase_worker(
            package_path=package_path,
            known_features=list(known_features),
            file_extension=file_extension,
            reporter=reporter,
        ),
    )
    return build_task_submission(task)
@traced_tool("map_codebase", component="tool.worker")
async def _map_codebase_worker(
    *,
    package_path: str,
    known_features: list[str],
    file_extension: str,
    reporter: ProgressReporter,
) -> dict:
    if not os.path.exists(package_path):
        return {"error": f"Package path not found: {package_path}"}

    await report_step(
        reporter,
        8,
        100,
        "prepare",
        f"Preparing codebase mapping for {package_path}.",
    )

    skills_content = await _load_skills()
    deps = MapDependencies(
        package_path=package_path,
        file_extension=file_extension,
        known_features=list(known_features),
        skills_content=skills_content,
    )

    await report_step(
        reporter,
        25,
        100,
        "scan",
        "Running the map agent to discover features and relationships.",
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

    await report_step(
        reporter,
        100,
        100,
        "complete",
        (
            f"Mapping finished with {len(report.features)} features and "
            f"{len(report.relationships)} relationships."
        ),
    )

    return {
        "status": "completed" if not report.partial_failure else "partial",
        "summary": report.summary,
        "entry_points": report.entry_points,
        "features_mapped": len(report.features),
        "relationships_mapped": len(report.relationships),
    }
