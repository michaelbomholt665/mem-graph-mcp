#!/usr/bin/env python3
# src/mem_graph/tools/agents/orchestrator.py
"""
MCP tool surface for the orchestrator agent.

FastMCP 3.0 upgrades:
- ``ctx: Context`` injected for progress reporting and client logging.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Literal

import anyio
from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field

from ...agents.orchestrator_agent import OrchestratorDependencies, orchestrator_agent
from ...agents.orchestrator_graph import autopilot_graph_run
from ...agents.router_agent import RouterDependencies, router_agent

mcp = FastMCP("orchestrator", instructions="Batch orchestration and recursive autopilot workflows.")
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
async def autopilot_remediate(
    project_id: Annotated[str, Field(description="Project ID to ground the remediation in.")],
    language: Annotated[Literal["go", "python", "typescript"], Field(description="Target language.")],
    target_files: Annotated[list[str], Field(description="Specific files to remediate.")],
    max_retries: Annotated[int, Field(description="Maximum refinement retry loops.", ge=1, le=5)] = 3,
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """
    Recursive Autopilot Remediation: Find, Fix, Style, Verify, and Sync.

    Uses the Router to select a model tier, then launches a pydantic-graph
    workflow that grounds itself in graph memory (Violations, Decisions)
    before proposing and validating code changes.
    """
    if ctx is not None:
        await ctx.info(f"Launching Autopilot Remediation for project {project_id} ({len(target_files)} files)")
        await ctx.report_progress(progress=0, total=3)

    # 1. Route and Tier Selection
    skills_content = await _load_skills()
    router_deps = RouterDependencies(
        project_id=project_id,
        request=f"Remediate violations in {len(target_files)} files: {', '.join(target_files)}",
        file_paths=target_files,
        skills_content=skills_content,
    )

    if ctx is not None:
        await ctx.info("Routing request and selecting model tier…")

    router_result = await router_agent.run("Classify intent and select tier.", deps=router_deps)
    decision = router_result.output

    if ctx is not None:
        await ctx.info(
            f"Selected Tier: {decision.tier.value} | Solo Mode: {decision.solo_mode} | "
            f"Concurrency: {decision.concurrency}"
        )
        await ctx.report_progress(progress=1, total=3)

    # 2. Launch Recursive Graph
    if ctx is not None:
        await ctx.info(f"Starting {decision.tier.value} workflow…")

    try:
        state = await autopilot_graph_run(
            language=language,
            target_files=target_files,
            project_id=project_id,
            tier=decision.tier.value,
            max_retries=max_retries,
        )
    except Exception as exc:
        logger.error("Autopilot graph failed: %s", exc)
        return {"error": f"Graph execution failed: {exc}"}

    if ctx is not None:
        await ctx.report_progress(progress=3, total=3)
        await ctx.info(f"Autopilot finished: {state.final_notes}")

    return {
        "status": "success" if state.success else "partial",
        "tier": state.tier,
        "language": state.language,
        "files_touched": len(state.styled_patches),
        "retries": state.retry_count,
        "summary": state.final_notes,
        "outcome": state.validation_status,
    }


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
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """
    Orchestrate batched analysis of a codebase with the audit, map, or decision sub-agents.

    The orchestrator reads files in bounded batches, injects pre-loaded file content
    into the selected sub-agent, aggregates results incrementally, and returns the
    merged output plus execution summary.
    """
    if not os.path.exists(package_path):
        return {"error": f"Package path not found: {package_path}"}

    if ctx is not None:
        await ctx.info(
            f"Starting orchestrated {subagent_name} analysis of {package_path} "
            f"(batch_size={batch_size})"
        )
        await ctx.report_progress(progress=0, total=3)

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

    if ctx is not None:
        await ctx.info(f"Running orchestrator agent ({subagent_name})…")
        await ctx.report_progress(progress=1, total=3)

    try:
        async with orchestrator_agent.run_stream(prompt, deps=deps) as result:
            report = await result.get_output()
    except Exception as exc:
        logger.error("Orchestrator execution failed: %s", exc)
        return {"error": f"Agent failed: {exc}"}

    if ctx is not None:
        await ctx.info(
            f"Orchestration complete: {report.total_files} files in "
            f"{report.total_batches} batches "
            f"({report.failed_batches} failed)."
        )
        await ctx.report_progress(progress=3, total=3)

    return {
        "status": "completed" if not report.partial_failure else "partial",
        "subagent": report.subagent_name,
        "summary": report.summary,
        "total_files": report.total_files,
        "total_batches": report.total_batches,
        "failed_batches": report.failed_batches,
        "aggregate": report.aggregate,
    }
