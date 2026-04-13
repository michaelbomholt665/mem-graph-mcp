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
from mcp.types import Icon
from pydantic import Field

from ...agents.orchestrator_agent import OrchestratorDependencies, orchestrator_agent
from ...agents.orchestrator_graph import autopilot_graph_run
from ...agents.router_agent import RouterDependencies, router_agent
from ...services.task_queue import task_queue
from ..background.progress import ContextProgressReporter, ProgressReporter, report_step
from ..background.task_status import build_task_submission

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


@mcp.tool(
    tags={"namespace:audit"},
    icons=[Icon(src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0Ij48cGF0aCBmaWxsPSIjMTYzYTVmIiBkPSJNMyAxOWgxOHYySDN6bTItM2gxNHYtMmgtMTR6bTQtM2gxMHYtMkg5em0yLTNoOHYtMkgxMXptMi0zaDZWNWgtNnoiLz48L3N2Zz4=", mimeType="image/svg+xml")],
    task=True,
)
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


@mcp.tool(tags={"namespace:audit"}, task=True)
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
    if ctx is not None and ctx.is_background_task:
        reporter = ContextProgressReporter(ctx)
        return await _orchestrate_codebase_worker(
            package_path=package_path,
            project_id=project_id,
            subagent_name=subagent_name,
            batch_size=batch_size,
            file_extension=file_extension,
            batch_timeout_seconds=batch_timeout_seconds,
            extra_context=extra_context,
            reporter=reporter,
        )

    task = await task_queue.enqueue(
        tool_name="orchestrate_codebase",
        arguments={
            "package_path": package_path,
            "project_id": project_id,
            "subagent_name": subagent_name,
            "batch_size": batch_size,
            "file_extension": file_extension,
            "batch_timeout_seconds": batch_timeout_seconds,
            "extra_context": extra_context or {},
        },
        session_id=ctx.session_id if ctx is not None else None,
        runner=lambda reporter: _orchestrate_codebase_worker(
            package_path=package_path,
            project_id=project_id,
            subagent_name=subagent_name,
            batch_size=batch_size,
            file_extension=file_extension,
            batch_timeout_seconds=batch_timeout_seconds,
            extra_context=extra_context,
            reporter=reporter,
        ),
    )
    return build_task_submission(task)


async def _orchestrate_codebase_worker(
    *,
    package_path: str,
    project_id: str,
    subagent_name: Literal["audit", "map", "decision"],
    batch_size: int,
    file_extension: str,
    batch_timeout_seconds: float,
    extra_context: dict[str, Any] | None,
    reporter: ProgressReporter,
) -> dict[str, Any]:
    if not os.path.exists(package_path):
        return {"error": f"Package path not found: {package_path}"}

    await report_step(
        reporter,
        8,
        100,
        "prepare",
        (
            f"Preparing orchestrated {subagent_name} analysis for {package_path} "
            f"with batch size {batch_size}."
        ),
    )

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

    await report_step(
        reporter,
        24,
        100,
        "orchestrate",
        f"Running the orchestrator agent for the {subagent_name} workflow.",
    )

    try:
        async with orchestrator_agent.run_stream(prompt, deps=deps) as result:
            report = await result.get_output()
    except Exception as exc:
        logger.error("Orchestrator execution failed: %s", exc)
        return {"error": f"Agent failed: {exc}"}

    await report_step(
        reporter,
        100,
        100,
        "complete",
        (
            f"Orchestration finished across {report.total_files} files and "
            f"{report.total_batches} batches."
        ),
    )

    return {
        "status": "completed" if not report.partial_failure else "partial",
        "subagent": report.subagent_name,
        "summary": report.summary,
        "total_files": report.total_files,
        "total_batches": report.total_batches,
        "failed_batches": report.failed_batches,
        "aggregate": report.aggregate,
    }
