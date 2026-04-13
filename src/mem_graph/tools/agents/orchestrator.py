#!/usr/bin/env python3
# src/mem_graph/tools/agents/orchestrator.py
"""MCP tool surface for the orchestrator agent."""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Literal

import anyio
from fastmcp import FastMCP
from pydantic import Field

from ...agents.orchestrator_agent import OrchestratorDependencies, orchestrator_agent

mcp = FastMCP("orchestrator", instructions="Batch orchestration for audit, map, and decision agents.")
logger = logging.getLogger(__name__)

_SKILLS_PATH = os.path.join(os.getcwd(), "skills", "orchestrator_agent", "SKILL.md")


async def _load_skills() -> str:
    if not os.path.exists(_SKILLS_PATH):
        return ""

    try:
        async with await anyio.open_file(_SKILLS_PATH, "r", encoding="utf-8") as handle:
            return await handle.read()
    except Exception as exc:
        logger.warning("Failed to load skills from %s: %s", _SKILLS_PATH, exc)
        return ""


@mcp.tool(tags={"namespace:audit"})
async def orchestrate_codebase(
    package_path: Annotated[str, Field(description="Absolute path to the package directory to analyse in batches.")],
    project_id: Annotated[str, Field(description="Project ID used by downstream sub-agents.")],
    subagent_name: Annotated[
        Literal["audit", "map", "decision"],
        Field(description="Which sub-agent to run for each batch."),
    ] = "audit",
    batch_size: Annotated[int, Field(description="Maximum files to analyse per batch.", ge=1, le=20)] = 5,
    file_extension: Annotated[str, Field(description="Source file extension to analyse. Defaults to '.py'.")] = ".py",
    batch_timeout_seconds: Annotated[
        float,
        Field(description="Per-batch timeout in seconds.", gt=0.0, le=600.0),
    ] = 120.0,
    extra_context: Annotated[
        dict[str, Any] | None,
        Field(description="Optional sub-agent-specific context, such as decision records or known features."),
    ] = None,
) -> dict[str, Any]:
    """
    Orchestrate batched analysis of a codebase with the audit, map, or decision sub-agents.

    The orchestrator reads files in bounded batches, injects pre-loaded file content
    into the selected sub-agent, aggregates results incrementally, and returns the
    merged output plus execution summary.
    """
    if not os.path.exists(package_path):
        return {"error": f"Package path not found: {package_path}"}

    skills_content = await _load_skills()
    deps = OrchestratorDependencies(
        package_path=package_path,
        project_id=project_id,
        subagent_name=subagent_name,
        file_extension=file_extension,
        batch_size=batch_size,
        timeout=batch_timeout_seconds,
        skills_content=skills_content,
        extra_context=extra_context or {},
    )

    prompt = (
        "List the files, process every batch in order using process_batch, "
        "and call finalize once all batches are complete."
    )

    try:
        async with orchestrator_agent.run_stream(prompt, deps=deps) as result:
            report = await result.get_output()
    except Exception as exc:
        logger.error("Orchestrator execution failed: %s", exc)
        return {"error": f"Agent failed: {exc}"}

    return {
        "status": "completed" if not report.partial_failure else "partial",
        "subagent": report.subagent_name,
        "summary": report.summary,
        "total_files": report.total_files,
        "total_batches": report.total_batches,
        "failed_batches": report.failed_batches,
        "aggregate": report.aggregate,
    }