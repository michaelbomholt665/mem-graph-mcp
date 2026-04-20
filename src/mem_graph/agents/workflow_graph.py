#!/usr/bin/env python3
# src/mem_graph/agents/workflow_graph.py
"""Opt-in managed sub-agent workflow graph.

Deprecation note:
  Primary workflow ownership has moved to
  ``mem_graph.workflows.runtime.managed_workflow_runtime``.
  This module retains the graph/node definitions and ``run_managed_workflow``
  for backward compatibility. New callers should import from
  ``mem_graph.workflows.runtime.managed_workflow_runtime`` and use
  ``run_managed_workflow_with_selection`` for profile-aware execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ..config import WorkflowStageName, config_get_model_for_workflow_stage
from ..resources.personas import PERSONA_REGISTRY
from ..resources.prompts import PROMPT_REGISTRY
from .router_agent import WorkflowPlan


class WorkflowStageResult(BaseModel):
    """Recorded result for a workflow graph stage."""

    stage: WorkflowStageName
    model: str
    allowed_tools: list[str]
    status: str = "completed"
    notes: str = ""


class ManagedWorkflowState(BaseModel):
    """Typed state for the opt-in one-prompt sub-agent workflow."""

    objective: str
    project_id: str
    target_files: list[str] = Field(default_factory=list)
    model_overrides: dict[str, str] = Field(default_factory=dict)
    max_retries: int = 3
    retry_count: int = 0
    execute_agents: bool = False
    ask_user_policy: str = (
        "Continue without stopping unless there is a hard blocker, "
        "destructive action, or missing required credentials/config."
    )
    file_contents: dict[str, str] = Field(default_factory=dict)
    implementation_output: dict[str, Any] = Field(default_factory=dict)
    audit_output: dict[str, Any] = Field(default_factory=dict)
    validation_output: dict[str, Any] = Field(default_factory=dict)
    documentation_output: dict[str, Any] = Field(default_factory=dict)
    context_map_output: dict[str, Any] = Field(default_factory=dict)
    sandbox_session_id: str = ""
    sandbox_workspace_path: str = ""
    sandbox_artifact: dict[str, Any] = Field(default_factory=dict)
    stage_results: list[WorkflowStageResult] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    final_report: str = ""


_READ_TOOLS = ["file_read", "file_search", "file_grep"]
_WRITE_TOOLS = ["file_read", "file_search", "file_grep", "file_edit", "file_write"]


class ContextGatherNode(BaseNode[ManagedWorkflowState, None, ManagedWorkflowState]):
    """Gather project context using read-only filesystem tools."""

    async def run(
        self,
        ctx: GraphRunContext[ManagedWorkflowState],
    ) -> "PlanWorkflowNode":
        ctx.state.file_contents = _read_target_files(ctx.state.target_files)
        _record_stage(ctx.state, "context_gather", _READ_TOOLS)
        return PlanWorkflowNode()


class PlanWorkflowNode(BaseNode[ManagedWorkflowState, None, ManagedWorkflowState]):
    """Create the stage plan from the starting objective and known context."""

    async def run(
        self,
        ctx: GraphRunContext[ManagedWorkflowState],
    ) -> "ImplementationNode":
        _record_stage(ctx.state, "planning", _READ_TOOLS)
        return ImplementationNode()


class ImplementationNode(BaseNode[ManagedWorkflowState, None, ManagedWorkflowState]):
    """Run implementation work with write-capable filesystem tools."""

    async def run(
        self,
        ctx: GraphRunContext[ManagedWorkflowState],
    ) -> "AuditNode":
        if ctx.state.execute_agents:
            try:
                from .fix.fixer_agent import FixerDependencies, fixer_agent

                deps = FixerDependencies(
                    violations=[ctx.state.objective],
                    file_contents=ctx.state.file_contents,
                    tier=config_get_model_for_workflow_stage(
                        "implementation",
                        ctx.state.model_overrides,
                    ),
                    project_id=ctx.state.project_id,
                )
                result = await fixer_agent.run(
                    "Implement the requested change using the provided file context. "
                    "Return a FixerReport.",
                    deps=deps,
                )
                ctx.state.implementation_output = result.output.model_dump(mode="json")
            except Exception as exc:  # noqa: BLE001
                ctx.state.blockers.append(f"implementation: {exc}")
        _record_stage(ctx.state, "implementation", _WRITE_TOOLS)
        return AuditNode()


class AuditNode(BaseNode[ManagedWorkflowState, None, ManagedWorkflowState]):
    """Audit implementation output before validation/debug routing."""

    async def run(
        self,
        ctx: GraphRunContext[ManagedWorkflowState],
    ) -> "DebugOrValidationNode":
        if ctx.state.execute_agents:
            try:
                from .audit.audit_agent import AuditDependencies, audit_agent

                deps = AuditDependencies(
                    package_path=".",
                    extra_file_context=_format_file_context(ctx.state.file_contents),
                    mode="preloaded",
                )
                result = await audit_agent.run(
                    "Audit the current workflow file context and return an AuditReport.",
                    deps=deps,
                )
                ctx.state.audit_output = result.output.model_dump(mode="json")
            except Exception as exc:  # noqa: BLE001
                ctx.state.blockers.append(f"audit: {exc}")
        _record_stage(ctx.state, "audit", _READ_TOOLS)
        return DebugOrValidationNode()


class DebugOrValidationNode(BaseNode[ManagedWorkflowState, None, ManagedWorkflowState]):
    """Run validation/debugging and decide whether to continue."""

    async def run(
        self,
        ctx: GraphRunContext[ManagedWorkflowState],
    ) -> "ImplementationNode | DocumentationNode":
        ctx.state.validation_output = {
            "status": "blocked" if ctx.state.blockers else "ready",
            "blockers": list(ctx.state.blockers),
            "retry_count": ctx.state.retry_count,
        }
        _record_stage(ctx.state, "debug_validation", _WRITE_TOOLS)
        if (
            ctx.state.execute_agents
            and not ctx.state.blockers
            and _audit_requires_retry(ctx.state)
            and ctx.state.retry_count < ctx.state.max_retries
        ):
            ctx.state.retry_count += 1
            ctx.state.validation_output["status"] = "retry"
            ctx.state.validation_output["retry_count"] = ctx.state.retry_count
            return ImplementationNode()
        return DocumentationNode()


class DocumentationNode(BaseNode[ManagedWorkflowState, None, ManagedWorkflowState]):
    """Update project-facing documentation for the completed work."""

    async def run(
        self,
        ctx: GraphRunContext[ManagedWorkflowState],
    ) -> "ContextMapUpdateNode":
        if ctx.state.execute_agents:
            try:
                from .document.scribe_agent import ScribeDependencies, scribe_agent

                patch_contents = _implementation_patch_contents(ctx.state)
                deps = ScribeDependencies(
                    language="python",
                    file_contents=patch_contents or ctx.state.file_contents,
                )
                result = await scribe_agent.run(
                    "Review documentation and style for the current workflow output. "
                    "Return a ScribeReport.",
                    deps=deps,
                )
                ctx.state.documentation_output = result.output.model_dump(mode="json")
            except Exception as exc:  # noqa: BLE001
                ctx.state.blockers.append(f"documentation: {exc}")
        _record_stage(ctx.state, "documentation", _WRITE_TOOLS)
        return ContextMapUpdateNode()


class ContextMapUpdateNode(BaseNode[ManagedWorkflowState, None, ManagedWorkflowState]):
    """Refresh context maps after implementation and documentation."""

    async def run(
        self,
        ctx: GraphRunContext[ManagedWorkflowState],
    ) -> "MemoryBankSyncNode":
        if ctx.state.execute_agents:
            try:
                from .map.map_agent import MapDependencies, map_agent

                deps = MapDependencies(
                    package_path=".",
                    extra_file_context=_format_file_context(ctx.state.file_contents),
                )
                result = await map_agent.run(
                    "Map the workflow file context and return a MapReport.",
                    deps=deps,
                )
                ctx.state.context_map_output = result.output.model_dump(mode="json")
            except Exception as exc:  # noqa: BLE001
                ctx.state.blockers.append(f"context_map_update: {exc}")
        _record_stage(ctx.state, "context_map_update", _WRITE_TOOLS)
        return MemoryBankSyncNode()


class MemoryBankSyncNode(BaseNode[ManagedWorkflowState, None, ManagedWorkflowState]):
    """Sync memory-bank state before the final report."""

    async def run(
        self,
        ctx: GraphRunContext[ManagedWorkflowState],
    ) -> "FinalReportNode":
        ctx.state.validation_output.setdefault(
            "memory_bank_sync",
            {
                "project_id": ctx.state.project_id,
                "stage_count": len(ctx.state.stage_results) + 1,
                "blocker_count": len(ctx.state.blockers),
            },
        )
        _record_stage(ctx.state, "memory_bank_sync", _WRITE_TOOLS)
        return FinalReportNode()


class FinalReportNode(BaseNode[ManagedWorkflowState, None, ManagedWorkflowState]):
    """Produce a deterministic final workflow report."""

    async def run(
        self,
        ctx: GraphRunContext[ManagedWorkflowState],
    ) -> End[ManagedWorkflowState]:
        stages = ", ".join(result.stage for result in ctx.state.stage_results)
        status = "blocked" if ctx.state.blockers else "completed"
        ctx.state.final_report = (
            f"Workflow {status} for project {ctx.state.project_id}: {stages}."
        )
        return End(ctx.state)


managed_workflow_graph = Graph[ManagedWorkflowState, None, ManagedWorkflowState](
    nodes=[
        ContextGatherNode,
        PlanWorkflowNode,
        ImplementationNode,
        AuditNode,
        DebugOrValidationNode,
        DocumentationNode,
        ContextMapUpdateNode,
        MemoryBankSyncNode,
        FinalReportNode,
    ]
)


async def run_managed_workflow(
    plan: WorkflowPlan,
    *,
    execute_agents: bool = False,
) -> ManagedWorkflowState:
    """
    Run the opt-in managed workflow from a single router-produced plan.

    This graph establishes Python-owned stage control and typed state. Stage
    internals can attach concrete sub-agent calls without changing routing.
    """
    state = ManagedWorkflowState(
        objective=plan.objective,
        project_id=plan.project_id,
        target_files=plan.target_files,
        model_overrides=plan.model_overrides,
        max_retries=plan.max_retries,
        execute_agents=execute_agents,
        ask_user_policy=plan.ask_user_policy,
    )
    result = await managed_workflow_graph.run(ContextGatherNode(), state=state)
    return result.output if result.output is not None else state


def _record_stage(
    state: ManagedWorkflowState,
    stage: WorkflowStageName,
    allowed_tools: list[str],
) -> None:
    persona_key = _stage_persona_key(stage)
    prompt_key = _stage_prompt_key(stage)
    persona = PERSONA_REGISTRY[persona_key]
    prompt = PROMPT_REGISTRY[prompt_key]
    state.stage_results.append(
        WorkflowStageResult(
            stage=stage,
            model=config_get_model_for_workflow_stage(stage, state.model_overrides),
            allowed_tools=allowed_tools,
            notes=(
                f"{persona.name} persona with {prompt_key} prompt "
                f"({len(prompt)} chars)."
            ),
        )
    )


def _stage_persona_key(stage: WorkflowStageName) -> str:
    if stage in {"implementation", "debug_validation"}:
        return "mechanic"
    if stage == "audit":
        return "auditor"
    if stage == "documentation":
        return "scribe"
    if stage == "context_map_update":
        return "mapper"
    if stage == "memory_bank_sync":
        return "chat"
    return "router"


def _stage_prompt_key(stage: WorkflowStageName) -> str:
    if stage == "memory_bank_sync":
        return "sync_context"
    return "workflow_agent"


def _read_target_files(paths: list[str]) -> dict[str, str]:
    contents: dict[str, str] = {}
    for path in paths:
        try:
            contents[path] = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            contents[path] = f"ERROR: {exc}"
    return contents


def _format_file_context(file_contents: dict[str, str]) -> str:
    return "\n\n".join(
        f"### {path}\n```\n{content}\n```"
        for path, content in file_contents.items()
    )


def _implementation_patch_contents(state: ManagedWorkflowState) -> dict[str, str]:
    patches = state.implementation_output.get("patches")
    if not isinstance(patches, list):
        return {}
    contents: dict[str, str] = {}
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        file_path = patch.get("file_path")
        proposed = patch.get("proposed_snippet")
        if isinstance(file_path, str) and isinstance(proposed, str):
            contents[file_path] = proposed
    return contents


def _audit_requires_retry(state: ManagedWorkflowState) -> bool:
    stats = state.audit_output.get("stats")
    if not isinstance(stats, dict):
        return False
    blocker_count = stats.get("blocker_count", 0)
    critical_count = stats.get("critical_count", 0)
    return bool(blocker_count or critical_count)
