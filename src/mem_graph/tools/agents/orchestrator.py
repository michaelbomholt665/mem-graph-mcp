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
from pydantic_ai.usage import RunUsage

from ...agents.orchestrator_agent import (
    OrchestratorDependencies,
    list_source_files,
    run_orchestrator_batches,
)
from ...agents.router_agent import RouterDependencies, router_agent
from ...app.registry import AgentEntry, register_agent
from ...config import config_build_orchestrator_usage_limits
from ...models.agent_outputs import BatchResult, WorkflowPlan
from ...resources.workflows.selection.selector import select_all
from ...services.task_queue import task_queue
from ...workflows.runtime.managed_workflow_runtime import (
    run_managed_workflow_with_selection,
)
from ...workflows.runtime.orchestrator_runtime import autopilot_graph_run_with_selection
from ..background.progress import ContextProgressReporter, ProgressReporter, report_step
from ..background.task_status import build_task_submission
from ..markers import tier_2_tool

mcp = FastMCP(
    "orchestrator",
    instructions="Batch orchestration and recursive autopilot workflows.",
)
logger = logging.getLogger(__name__)

register_agent(
    AgentEntry(
        name="Autopilot Remediation",
        tool_name="autopilot_remediate",
        description="Recursive Find, Fix, Style, Verify, and Sync.",
        namespace="audit",
        categories=["code", "remediation"],
        task_types=["remediation", "refactoring", "bug_fix"],
    )
)
register_agent(
    AgentEntry(
        name="Codebase Orchestrator",
        tool_name="orchestrate_codebase",
        description="Batched analysis orchestration across sub-agents.",
        namespace="audit",
        categories=["coordination", "code"],
        task_types=["batched_audit", "batched_mapping", "batched_decision_review"],
    )
)
register_agent(
    AgentEntry(
        name="Sub-agent Workflow",
        tool_name="run_subagent_workflow",
        description="Managed multi-stage routing workflow.",
        namespace="audit",
        categories=["coordination", "workflow"],
        task_types=["subagent_workflow", "managed_workflow"],
    )
)

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


@tier_2_tool
@mcp.tool(
    tags={"namespace:audit"},
    icons=[
        Icon(
            src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0Ij48cGF0aCBmaWxsPSIjMTYzYTVmIiBkPSJNMyAxOWgxOHYySDN6bTItM2gxNHYtMmgtMTR6bTQtM2gxMHYtMkg5em0yLTNoOHYtMkgxMXptMi0zaDZWNWgtNnoiLz48L3N2Zz4=",
            mimeType="image/svg+xml",
        )
    ],
    task=True,
)
async def autopilot_remediate(
    project_id: Annotated[
        str, Field(description="Project ID to ground the remediation in.")
    ],
    language: Annotated[
        Literal["go", "python", "typescript"], Field(description="Target language.")
    ],
    target_files: Annotated[
        list[str], Field(description="Specific files to remediate.")
    ],
    task: Annotated[
        str | None, Field(description="Optional remediation task or objective.")
    ] = None,
    max_retries: Annotated[
        int, Field(description="Maximum refinement retry loops.", ge=1, le=5)
    ] = 3,
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Run the recursive remediation workflow for selected files."""
    if ctx is not None:
        await ctx.info(
            f"Launching Autopilot Remediation for project {project_id} ({len(target_files)} files)"
        )
        await ctx.report_progress(progress=0, total=3)

    # 1. Route and Tier Selection
    skills_content = await _load_skills()

    # Combine task into request
    request_msg = (
        f"Remediate violations in {len(target_files)} files: {', '.join(target_files)}"
    )
    if task:
        request_msg = f"{task}\n\nScope: {request_msg}"

    router_deps = RouterDependencies(
        project_id=project_id,
        request=request_msg,
        file_paths=target_files,
        skills_content=skills_content,
    )

    if ctx is not None:
        await ctx.info("Routing request and selecting model tier…")

    router_result = await router_agent.run(
        "Classify intent and select tier.", deps=router_deps
    )
    decision = router_result.output

    if ctx is not None:
        await ctx.info(
            f"Selected Tier: {decision.tier.value} | Solo Mode: {decision.solo_mode} | "
            f"Concurrency: {decision.concurrency}"
        )
        await ctx.report_progress(progress=1, total=3)

    # 2. Select workflow profile and launch recursive graph
    task_type = (
        decision.intent
        if decision.intent in ("remediation", "refactoring", "bug_fix")
        else "remediation"
    )
    selection = select_all(
        task_type,
        file_count=len(target_files),
        risk_level="high",
    )
    if ctx is not None:
        await ctx.info(
            f"Workflow profile: {selection.effective_size.value} "
            f"| Reasoning: {selection.reasoning_policy.mode.value}"
        )
        await ctx.info(
            "Sandbox policy: "
            f"{'enabled' if selection.sandbox_policy.enabled else 'disabled'} "
            f"| network={selection.sandbox_policy.network}"
        )
        await ctx.info(f"Starting {decision.tier.value} workflow…")

    try:
        state = await autopilot_graph_run_with_selection(
            language=language,
            target_files=target_files,
            project_id=project_id,
            tier=decision.tier.value,
            max_retries=max_retries,
            selection=selection,
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
        "sandbox": state.sandbox_artifact,
    }


@tier_2_tool
@mcp.tool(tags={"namespace:audit"}, task=True)
async def orchestrate_codebase(
    package_path: Annotated[
        str,
        Field(
            description="Absolute path to the package directory to analyse in batches."
        ),
    ],
    project_id: Annotated[
        str, Field(description="Project ID used by downstream sub-agents.")
    ],
    subagent_name: Annotated[
        Literal[
            "audit", "security_audit", "bug_audit", "smell_audit", "map", "decision"
        ],
        Field(description="Which sub-agent to run for each batch."),
    ] = "audit",
    batch_size: Annotated[
        int, Field(description="Maximum files to analyse per batch.", ge=1, le=20)
    ] = 5,
    file_extension: Annotated[
        str, Field(description="Source file extension to analyse. Defaults to '.py'.")
    ] = ".py",
    batch_timeout_seconds: Annotated[
        float,
        Field(description="Per-batch timeout in seconds.", gt=0.0, le=600.0),
    ] = 120.0,
    extra_context: Annotated[
        dict[str, Any] | None,
        Field(
            description="Optional sub-agent-specific context, such as decision records or known features."
        ),
    ] = None,
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Run batched sub-agent analysis over a codebase."""
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


@tier_2_tool
@mcp.tool(tags={"namespace:audit"}, task=True)
async def run_subagent_workflow(
    objective: Annotated[
        str, Field(description="One starting prompt/objective for the full workflow.")
    ],
    project_id: Annotated[
        str, Field(description="Project ID to ground the workflow in.")
    ],
    target_files: Annotated[list[str], Field(description="Files initially in scope.")],
    project_root: Annotated[
        str, Field(description="Project root for helper-agent lookup.")
    ] = "",
    max_retries: Annotated[
        int, Field(description="Maximum validation/debug retries.", ge=0, le=10)
    ] = 3,
    model_overrides: Annotated[
        dict[str, str] | None,
        Field(
            description="Optional per-stage model overrides keyed by workflow stage."
        ),
    ] = None,
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Run the managed router-driven sub-agent workflow."""
    if ctx is not None:
        await ctx.info(f"Routing managed workflow for project {project_id}")
        await ctx.report_progress(progress=0, total=3)

    router_deps = RouterDependencies(
        project_id=project_id,
        request=objective,
        file_paths=target_files,
        project_root=project_root,
        workflow_mode="subagent_workflow",
        model_overrides=model_overrides or {},
        max_retries=max_retries,
    )
    router_result = await router_agent.run(
        "Classify this objective and return a subagent_workflow plan.",
        deps=router_deps,
    )
    decision = router_result.output
    plan = decision.workflow_plan or WorkflowPlan(
        objective=objective,
        project_id=project_id,
        target_files=target_files,
        model_overrides=model_overrides or {},
        max_retries=max_retries,
    )

    if ctx is not None:
        selection = select_all(
            "subagent_workflow",
            file_count=len(target_files),
            risk_level="medium",
        )
        await ctx.info(
            "Starting managed workflow graph "
            f"(sandbox={'enabled' if selection.sandbox_policy.enabled else 'disabled'})"
        )
        await ctx.report_progress(progress=1, total=3)
    else:
        selection = select_all(
            "subagent_workflow",
            file_count=len(target_files),
            risk_level="medium",
        )

    state = await run_managed_workflow_with_selection(
        plan,
        execute_agents=True,
        selection=selection,
        task_type="subagent_workflow",
        risk_level="medium",
    )

    if ctx is not None:
        await ctx.report_progress(progress=3, total=3)
        await ctx.info(state.final_report)

    return {
        "status": "blocked" if state.blockers else "completed",
        "project_id": state.project_id,
        "objective": state.objective,
        "stages": [result.model_dump(mode="json") for result in state.stage_results],
        "blockers": state.blockers,
        "summary": state.final_report,
        "sandbox": state.sandbox_artifact,
    }


async def _orchestrate_codebase_worker(
    *,
    package_path: str,
    project_id: str,
    subagent_name: Literal[
        "audit",
        "security_audit",
        "bug_audit",
        "smell_audit",
        "map",
        "decision",
    ],
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
    file_count = len(list_source_files(package_path, file_extension))
    total_batches = max(1, (file_count + max(batch_size, 1) - 1) // max(batch_size, 1))
    deps = OrchestratorDependencies(
        package_path=package_path,
        project_id=project_id,
        subagent_name=subagent_name,
        file_extension=file_extension,
        batch_size=batch_size,
        timeout=batch_timeout_seconds,
        skills_content=skills_content,
        extra_context=extra_context or {},
        usage_limits=config_build_orchestrator_usage_limits(total_batches),
    )

    await report_step(
        reporter,
        24,
        100,
        "orchestrate",
        f"Running deterministic {subagent_name} batch orchestration.",
    )

    try:

        async def on_batch(
            batch_number: int,
            total_batches: int,
            result: BatchResult,
        ) -> None:
            progress = 24 + int((batch_number / max(total_batches, 1)) * 70)
            status = "failed" if result.failed else "completed"
            await report_step(
                reporter,
                min(progress, 94),
                100,
                "batch",
                (
                    f"Batch {batch_number}/{total_batches} {status} "
                    f"for {len(result.files_processed)} file(s)."
                ),
            )

        job_usage = RunUsage()
        report = await run_orchestrator_batches(
            deps, progress_callback=on_batch, usage=job_usage
        )
    except Exception as exc:
        logger.error("Orchestrator execution failed: %s", exc)
        return {"error": f"Orchestration failed: {exc}"}

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
        "usage": {
            "requests": job_usage.requests,
            "input_tokens": job_usage.input_tokens,
            "output_tokens": job_usage.output_tokens,
        },
    }
