#!/usr/bin/env python3
# src/mem_graph/agents/orchestrator_graph.py
"""
Orchestrator Graph Engine: Recursive Autopilot Workflow.

Implements a six-node pydantic-graph with a deterministic retry loop for
the multi-agent execution engine. Enforces the Context-Sentry-Draft-Style-
Guard-Sync lifecycle for Go, Python, and TypeScript. The graph grounds
every run in the current graph state before acting and persists results
upon completion.

Workflow:
  ContextGather → Sentry → LogicDraft → StyleDraft → Guard
                                    ↓           ↓
                                MemorySync ← Refine (retry)
                                    ↓
                                    End

Deprecation note:
  Primary workflow ownership has moved to
  ``mem_graph.workflows.runtime.orchestrator_runtime``.
  This module retains the graph/node definitions and ``autopilot_graph_run``
  for backward compatibility. New callers should import from
  ``mem_graph.workflows.runtime.orchestrator_runtime`` and use
  ``autopilot_graph_run_with_selection`` for profile-aware execution.
"""

from __future__ import annotations

################
#   IMPORTS
################
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Literal, Union, cast

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ..config import ModelTier
from ..observability import traced_span

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)
_NEXT_NODE_ATTR = "graph.next_node"

################
#   STATE
################


class AutopilotState(BaseModel):
    """
    Shared state for the Recursive Autopilot execution.

    Passed through every node of the graph. Each node reads what it
    needs and writes its results back before returning the next node.

    Attributes:
        language: Source language being processed (go, python, typescript).
        target_files: File paths in scope for this autopilot run.
        project_id: The project node ID for graph context queries.
        tier: Model tier selected by the Router for this run.
        context_violations: Open violation summaries from the graph.
        context_decisions: Active decision summaries from the graph.
        context_map: Codebase map summary from the graph.
        file_contents: Pre-read file contents keyed by path.
        fixer_patches: Proposed logic changes keyed by file path.
        styled_patches: Style-corrected content keyed by file path.
        validation_violations: Violations found during validation.
        validation_status: 'approved' or 'rejected'.
        retry_count: How many refinement loops have been attempted.
        max_retries: Maximum allowed retry loops before forced exit.
        final_notes: Note content written to the graph on completion.
        success: Whether the autopilot run completed successfully.
    """

    language: Literal["go", "python", "typescript"] = "python"
    target_files: list[str] = Field(default_factory=list)
    project_id: str = ""
    tier: str = ModelTier.STANDARD.value

    # Context gathered from graph
    context_violations: list[str] = Field(default_factory=list)
    context_decisions: list[str] = Field(default_factory=list)
    context_map: str = ""
    manifest_context: dict[str, str] = Field(default_factory=dict)

    # File working area
    file_contents: dict[str, str] = Field(default_factory=dict)

    # Agent outputs
    sentry_tests: list[str] = Field(default_factory=list)
    fixer_patches: dict[str, str] = Field(default_factory=dict)
    styled_patches: dict[str, str] = Field(default_factory=dict)
    guard_output: str = ""
    validation_violations: list[str] = Field(default_factory=list)
    validation_status: str = "pending"

    # Control flow
    retry_count: int = 0
    max_retries: int = 3
    sandbox_session_id: str = ""
    sandbox_workspace_path: str = ""
    sandbox_artifact: dict[str, Any] = Field(default_factory=dict)
    final_notes: str = ""
    success: bool = False


################
#   NODE: CONTEXT GATHER
################


class ContextGatherNode(BaseNode[AutopilotState, None, AutopilotState]):
    """
    Step 1: Context Gathering.

    Queries the graph for open Violations, active Decisions, and the
    current codebase Map. Pre-reads target files from disk. This grounds
    the entire run before any agent makes a single edit.
    """

    async def run(
        self,
        ctx: GraphRunContext[AutopilotState],
    ) -> "SentryNode":
        """
        Gather graph context and pre-read target files.

        Args:
            ctx: The graph run context holding AutopilotState.

        Returns:
            LogicDraftNode to proceed to the logic draft phase.
        """
        with traced_span(
            "orchestrator.context_gather",
            attributes=_graph_span_attributes(ctx.state, "ContextGatherNode"),
        ) as span:
            logger.info(
                "[CONTEXT] Gathering graph context for project %s (%s, %d files)",
                ctx.state.project_id,
                ctx.state.language,
                len(ctx.state.target_files),
            )

            ctx.state.context_violations = _state_query_violations(ctx.state.project_id)
            ctx.state.context_decisions = _state_query_decisions(ctx.state.project_id)
            ctx.state.context_map = _state_query_map(ctx.state.project_id)
            ctx.state.manifest_context = _state_read_manifests()
            ctx.state.file_contents = _state_read_target_files(
                ctx.state.target_files
            )

            logger.info(
                "[CONTEXT] %d violations, %d decisions loaded.",
                len(ctx.state.context_violations),
                len(ctx.state.context_decisions),
            )
            next_node = SentryNode()
            span.set_attribute(_NEXT_NODE_ATTR, type(next_node).__name__)
            return next_node


################
#   NODE: SENTRY
################


class SentryNode(BaseNode[AutopilotState, None, AutopilotState]):
    """
    Step 2: Sentry (Test Architect).

    Drafts failing tests before the code-authoring stage so the graph
    has an explicit red-test target for the Mechanic to satisfy.
    """

    async def run(
        self,
        ctx: GraphRunContext[AutopilotState],
    ) -> "LogicDraftNode":
        """Run the Sentry Agent to produce a red-first test plan."""
        from .validate.sentry_agent import SentryDependencies, sentry_agent

        with traced_span(
            "orchestrator.sentry",
            attributes=_graph_span_attributes(ctx.state, "SentryNode"),
        ) as span:
            logger.info(
                "[SENTRY] Planning red tests for %d file(s) (project=%s)",
                len(ctx.state.target_files),
                ctx.state.project_id,
            )

            deps = SentryDependencies(
                language=ctx.state.language,
                file_contents=ctx.state.file_contents,
                manifest_context=ctx.state.manifest_context,
                context_violations=ctx.state.context_violations,
                context_decisions=ctx.state.context_decisions,
            )

            prompt = (
                "Draft the failing tests that should be written before the fix. "
                "Use sentry_read_file for file context and sentry_record_test for each test. "
                "Return a SentryReport."
            )
            result = await sentry_agent.run(prompt, deps=deps)
            report = result.output

            ctx.state.sentry_tests = [
                f"{test.file_path}::{test.test_name} — {test.failing_assertion}"
                for test in report.test_cases
            ]

            logger.info(
                "[SENTRY] %d test case(s) planned using %s.",
                len(report.test_cases),
                report.framework,
            )
            span.set_attribute("orchestrator.test_plan_count", len(report.test_cases))
            next_node = LogicDraftNode()
            span.set_attribute(_NEXT_NODE_ATTR, type(next_node).__name__)
            return next_node


################
#   NODE: LOGIC DRAFT
################


class LogicDraftNode(BaseNode[AutopilotState, None, AutopilotState]):
    """
    Step 3: Logic Draft (Fixer Agent).

    The Mechanic proposes functional code changes to resolve the violations
    loaded during context gathering. Operates at the Router-selected tier.
    On retry, passes the previous validation feedback so the agent refines
    its approach rather than repeating the same attempt.

    Parallelism: Batches file edits based on config scaling rules.
    """

    async def run(
        self,
        ctx: GraphRunContext[AutopilotState],
    ) -> "StyleDraftNode":
        """
        Run the Fixer Agent to produce logic patches.

        Args:
            ctx: The graph run context holding AutopilotState.

        Returns:
            StyleDraftNode to apply documentation standards next.
        """
        from ..config import config_get_concurrency_for_files, config_is_solo_mode
        from .fix.fixer_agent import FixerDependencies, fixer_agent

        with traced_span(
            "orchestrator.logic_draft",
            attributes=_graph_span_attributes(ctx.state, "LogicDraftNode"),
        ) as span:
            prefix = (
                f"[RETRY {ctx.state.retry_count}]"
                if ctx.state.retry_count
                else "[LOGIC]"
            )
            file_count = len(ctx.state.target_files)
            is_solo = config_is_solo_mode(
                file_count,
                high_complexity=(ctx.state.tier == ModelTier.AUTOPILOT.value),
            )
            concurrency = 1 if is_solo else config_get_concurrency_for_files(file_count)

            logger.info(
                "%s Running Fixer Agent (tier=%s, concurrency=%d, solo=%s)",
                prefix,
                ctx.state.tier,
                concurrency,
                is_solo,
            )

            violations_to_fix = list(ctx.state.context_violations)
            if ctx.state.validation_violations:
                violations_to_fix = ctx.state.validation_violations

            test_plan_context = "\n".join(
                f"  - {test}" for test in ctx.state.sentry_tests
            )
            batches = _split_into_batches(ctx.state.target_files, concurrency)
            all_patches: dict[str, str] = {}
            patches_lock = asyncio.Lock()

            import anyio

            async def worker(file_subset: list[str]) -> None:
                subset_contents = {
                    path: ctx.state.file_contents[path] for path in file_subset
                }
                deps = FixerDependencies(
                    violations=violations_to_fix,
                    file_contents=subset_contents,
                    tier=ctx.state.tier,
                    project_id=ctx.state.project_id,
                )
                prompt = (
                    f"Fix the violation(s) for the following files: {', '.join(file_subset)}. "
                    f"\nRed tests to satisfy:\n{test_plan_context or '  - None recorded.'}\n"
                    "Use fixer_read_file_context to inspect, fixer_record_patch for each fix. "
                    "Return your FixerReport."
                )
                res = await fixer_agent.run(prompt, deps=deps)
                worker_patches = {
                    p.file_path: p.proposed_snippet for p in res.output.patches
                }
                async with patches_lock:
                    all_patches.update(worker_patches)

            async with anyio.create_task_group() as tg:
                for batch in batches:
                    tg.start_soon(worker, batch)

            ctx.state.fixer_patches = all_patches
            logger.info(
                "[LOGIC] %d patch(es) produced across %d worker(s).",
                len(all_patches),
                len(batches),
            )
            span.set_attribute("orchestrator.patch_count", len(all_patches))
            span.set_attribute("orchestrator.worker_count", len(batches))
            next_node = StyleDraftNode()
            span.set_attribute(_NEXT_NODE_ATTR, type(next_node).__name__)
            return next_node


################
#   NODE: STYLE DRAFT
################


class StyleDraftNode(BaseNode[AutopilotState, None, AutopilotState]):
    """
    Step 4: Style Draft (Scribe Agent).

    The Stylist applies documentation standards to the logic patches from
    the Mechanic. Ensures all file headers, docstrings, and naming
    conventions are correct without modifying any functional logic.

    Parallelism: Batches styling based on config scaling rules.
    """

    async def run(
        self,
        ctx: GraphRunContext[AutopilotState],
    ) -> "GuardNode":
        """
        Run the Scribe Agent to apply coding standards.

        Args:
            ctx: The graph run context holding AutopilotState.

        Returns:
            GuardNode to run the quality gate next.
        """
        from ..config import config_get_concurrency_for_files
        from ..resources.architecture import ARCHITECTURE_GUARDRAILS
        from .document.scribe_agent import ScribeDependencies, scribe_agent

        with traced_span(
            "orchestrator.style_draft",
            attributes=_graph_span_attributes(ctx.state, "StyleDraftNode"),
        ) as span:
            file_count = len(ctx.state.fixer_patches)
            concurrency = config_get_concurrency_for_files(file_count)

            logger.info(
                "[STYLE] Running Scribe Agent (language=%s, concurrency=%d)",
                ctx.state.language,
                concurrency,
            )

            batches = _split_into_batches(
                list(ctx.state.fixer_patches.keys()),
                concurrency,
            )
            all_styled = {}

            import anyio

            async def worker(file_subset: list[str]) -> None:
                subset_contents = {
                    path: ctx.state.fixer_patches[path] for path in file_subset
                }
                deps = ScribeDependencies(
                    language=ctx.state.language,
                    file_contents=subset_contents,
                    architecture_guardrails=ARCHITECTURE_GUARDRAILS,
                )
                prompt = (
                    "Apply language coding standards to the provided file subset. "
                    "Return StyledFilePatches."
                )
                res = await scribe_agent.run(prompt, deps=deps)
                for p in res.output.styled_patches:
                    all_styled[p.file_path] = p.styled_content

            async with anyio.create_task_group() as tg:
                for batch in batches:
                    tg.start_soon(worker, batch)

            ctx.state.styled_patches = all_styled
            if not ctx.state.styled_patches:
                ctx.state.styled_patches = dict(ctx.state.fixer_patches)

            logger.info(
                "[STYLE] %d file(s) styled across %d worker(s).",
                len(all_styled),
                len(batches),
            )
            span.set_attribute(
                "orchestrator.styled_file_count", len(ctx.state.styled_patches)
            )
            span.set_attribute("orchestrator.worker_count", len(batches))
            next_node = GuardNode()
            span.set_attribute(_NEXT_NODE_ATTR, type(next_node).__name__)
            return next_node


################
#   NODE: GUARD
################


class GuardNode(BaseNode[AutopilotState, None, AutopilotState]):
    """
    Step 5: Guard (Deterministic Validation).

    Runs the repository's real CLI checks instead of asking an LLM to
    approve the patch set. Approves only when the Python quality gate
    passes and routes back to LogicDraft on failure.
    """

    async def run(
        self,
        ctx: GraphRunContext[AutopilotState],
    ) -> Union["MemorySyncNode", "LogicDraftNode"]:
        """Run deterministic validation commands and route based on exit status."""

        with traced_span(
            "orchestrator.guard",
            attributes=_graph_span_attributes(ctx.state, "GuardNode"),
        ) as span:
            logger.info(
                "[GUARD] Running CLI validation (retry=%d/%d)",
                ctx.state.retry_count,
                ctx.state.max_retries,
            )

            guard_success, guard_issues, guard_output = await _state_run_quality_gate()
            ctx.state.guard_output = guard_output
            ctx.state.validation_violations = guard_issues
            ctx.state.validation_status = "approved" if guard_success else "rejected"
            span.set_attribute("orchestrator.guard_issue_count", len(guard_issues))
            span.set_attribute("orchestrator.guard_success", guard_success)

            if guard_success:
                logger.info("[GUARD] APPROVED — proceeding to memory sync.")
                ctx.state.success = True
                span.set_attribute(_NEXT_NODE_ATTR, "MemorySyncNode")
                return MemorySyncNode()

            ctx.state.retry_count += 1
            if ctx.state.retry_count >= ctx.state.max_retries:
                logger.warning(
                    "[GUARD] REJECTED after %d retries — forcing memory sync with failure.",
                    ctx.state.retry_count,
                )
                ctx.state.success = False
                span.set_attribute(_NEXT_NODE_ATTR, "MemorySyncNode")
                return MemorySyncNode()

            logger.info(
                "[GUARD] REJECTED (%d issue(s)) — retrying (attempt %d/%d).",
                len(guard_issues),
                ctx.state.retry_count,
                ctx.state.max_retries,
            )
            span.set_attribute(_NEXT_NODE_ATTR, "LogicDraftNode")
            return LogicDraftNode()


################
#   NODE: MEMORY SYNC
################


class MemorySyncNode(BaseNode[AutopilotState, None, AutopilotState]):
    """
    Step 6: Memory Sync.

    Writes the autopilot run result to the graph:
    - Creates a Note node summarising what happened.
    - Updates Violation node statuses for resolved violations.
    - Records the run outcome for the next sync_context call.
    """

    async def run(
        self,
        ctx: GraphRunContext[AutopilotState],
    ) -> End[AutopilotState]:
        """
        Persist the run outcome to the graph and finalize the state.

        Args:
            ctx: The graph run context holding AutopilotState.

        Returns:
            End node wrapping the final AutopilotState.
        """
        with traced_span(
            "orchestrator.memory_sync",
            attributes=_graph_span_attributes(ctx.state, "MemorySyncNode"),
        ) as span:
            logger.info(
                "[SYNC] Persisting autopilot outcome (success=%s, project=%s)",
                ctx.state.success,
                ctx.state.project_id,
            )

            outcome = "SUCCESS" if ctx.state.success else "PARTIAL"
            status_emoji = "✅" if ctx.state.success else "⚠️"

            note_content = (
                f"{status_emoji} Autopilot run [{outcome}] — {ctx.state.language}\n"
                f"Files: {len(ctx.state.target_files)}\n"
                f"Tier: {ctx.state.tier}\n"
                f"Patches applied: {len(ctx.state.styled_patches)}\n"
                f"Retries: {ctx.state.retry_count}/{ctx.state.max_retries}\n"
                f"Validation status: {ctx.state.validation_status}"
            )

            if ctx.state.validation_violations:
                note_content += "\nOpen issues:\n" + "\n".join(
                    f"  - {v}" for v in ctx.state.validation_violations[:10]
                )

            ctx.state.final_notes = note_content
            _state_write_note(ctx.state.project_id, note_content)

            logger.info("[SYNC] Note written to graph. Autopilot complete.")
            span.set_attribute("autopilot.success", ctx.state.success)
            span.set_attribute(_NEXT_NODE_ATTR, "End")
            return End(ctx.state)


################
#   GRAPH
################

autopilot_graph = Graph[AutopilotState, None, AutopilotState](
    nodes=[
        ContextGatherNode,
        SentryNode,
        LogicDraftNode,
        StyleDraftNode,
        GuardNode,
        MemorySyncNode,
    ]
)


################
#   GRAPH ENTRY POINT
################


async def autopilot_graph_run(
    language: Literal["go", "python", "typescript"],
    target_files: list[str],
    project_id: str,
    tier: str = ModelTier.STANDARD.value,
    max_retries: int = 3,
) -> AutopilotState:
    """
    Launch the Recursive Autopilot workflow for a set of target files.

    The workflow: gathers graph context → Sentry drafts red tests → fixer
    drafts logic changes → scribe applies standards → deterministic guard
    runs the CLI checks → memory sync.
    Retries up to max_retries times on rejection before forcing completion.

    Args:
        language: Source language to process (go, python, typescript).
        target_files: File paths in scope for this autopilot run.
        project_id: The project node ID for graph context.
        tier: Model tier string from ModelTier enum.
        max_retries: Maximum refinement retry loops.

    Returns:
        Final AutopilotState with success flag and all intermediate outputs.
    """
    initial_state = AutopilotState(
        language=language,
        target_files=target_files,
        project_id=project_id,
        tier=tier,
        max_retries=max_retries,
    )

    with traced_span(
        "orchestrator.run",
        attributes={
            "autopilot.language": language,
            "autopilot.file_count": len(target_files),
            "autopilot.max_retries": max_retries,
            "autopilot.tier": tier,
            "project.id": project_id or "none",
        },
    ) as span:
        result = await autopilot_graph.run(ContextGatherNode(), state=initial_state)
        final_state = result.output if result.output is not None else initial_state
        span.set_attribute("autopilot.success", final_state.success)
        span.set_attribute("autopilot.retry_count", final_state.retry_count)
        return final_state


def _graph_span_attributes(
    state: AutopilotState,
    node_name: str,
) -> dict[str, str | bool | int]:
    return {
        "graph.node": node_name,
        "autopilot.language": state.language,
        "autopilot.file_count": len(state.target_files),
        "autopilot.retry_count": state.retry_count,
        "autopilot.max_retries": state.max_retries,
        "autopilot.tier": state.tier,
        "project.id": state.project_id or "none",
    }


################
#   GRAPH HELPERS
################


def _state_query_violations(project_id: str) -> list[str]:
    """
    Fetch open violation summaries from the graph for context grounding.

    Args:
        project_id: The project to query violations for.

    Returns:
        List of violation summary strings (rule:file:description).
    """
    if not project_id:
        return []
    try:
        from ..db import db_get_connection

        conn = db_get_connection()
        qr: Any = conn.execute(
            """
            MATCH (p:Project {id: $pid})-[:HAS_VIOLATION]->(v:Violation)
            WHERE v.status IN ['open', 'recurrence']
            RETURN v.rule, v.file_path, v.description
            LIMIT 50
            """,
            {"pid": project_id},
        )
        if isinstance(qr, list):
            qr = qr[0]
        rows: list[list[Any]] = cast(list[list[Any]], qr.get_all())
        return [f"{r[0]}:{r[1]}: {r[2][:120]}" for r in rows]
    except Exception as exc:
        logger.warning("Could not query violations: %s", exc)
        return []


def _state_query_decisions(project_id: str) -> list[str]:
    """
    Fetch active decision summaries from the graph for context grounding.

    Args:
        project_id: The project to query decisions for.

    Returns:
        List of decision summary strings (title: rationale).
    """
    if not project_id:
        return []
    try:
        from ..db import db_get_connection

        conn = db_get_connection()
        qr: Any = conn.execute(
            """
            MATCH (p:Project {id: $pid})-[:HAS_DECISION]->(d:Decision)
            WHERE d.status = 'active'
            RETURN d.title, d.rationale
            LIMIT 20
            """,
            {"pid": project_id},
        )
        if isinstance(qr, list):
            qr = qr[0]
        rows: list[list[Any]] = cast(list[list[Any]], qr.get_all())
        return [f"{r[0]}: {r[1][:150]}" for r in rows]
    except Exception as exc:
        logger.warning("Could not query decisions: %s", exc)
        return []


def _state_query_map(project_id: str) -> str:
    """
    Fetch a compact codebase map summary from the graph.

    Args:
        project_id: The project to retrieve the map for.

    Returns:
        A short string summary of the current codebase map, or empty string.
    """
    if not project_id:
        return ""
    try:
        from ..db import db_get_connection

        conn = db_get_connection()
        qr: Any = conn.execute(
            """
            MATCH (p:Project {id: $pid})-[:HAS_NOTE]->(n:Note)
            WHERE n.kind = 'map'
            RETURN n.content
            ORDER BY n.created_at DESC
            LIMIT 1
            """,
            {"pid": project_id},
        )
        if isinstance(qr, list):
            qr = qr[0]
        rows: list[list[Any]] = cast(list[list[Any]], qr.get_all())
        return str(rows[0][0]) if rows else ""
    except Exception as exc:
        logger.warning("Could not query map: %s", exc)
        return ""


def _state_read_target_files(file_paths: list[str]) -> dict[str, str]:
    """
    Read a list of target files into an in-memory dict.

    Files that cannot be read are included with an error message so
    agents always receive the full dict without missing keys.

    Args:
        file_paths: Absolute or repo-relative file paths to read.

    Returns:
        Dict mapping file_path to content string.
    """
    contents: dict[str, str] = {}
    _MAX_BYTES = 64_000

    for path in file_paths:
        try:
            raw = Path(path).read_bytes()
            if len(raw) > _MAX_BYTES:
                contents[path] = (
                    raw[:_MAX_BYTES].decode("utf-8", errors="replace") + "\n[TRUNCATED]"
                )
            else:
                contents[path] = raw.decode("utf-8", errors="replace")
        except Exception as exc:
            contents[path] = f"ERROR: {exc}"

    return contents


def _state_read_manifests() -> dict[str, str]:
    """Read repository manifests used by the manifest guard."""
    manifests: dict[str, str] = {}
    root = _workspace_root()

    for relative_path in ("pyproject.toml", "go.mod", "package.json"):
        path = root / relative_path
        try:
            if path.exists():
                manifests[relative_path] = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            manifests[relative_path] = f"ERROR: {exc}"

    return manifests


async def _state_run_quality_gate() -> tuple[bool, list[str], str]:
    """Run the deterministic Python quality gate and return CLI output."""
    commands = [
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "mypy", "."],
    ]

    outputs: list[str] = []
    issues: list[str] = []
    success = True

    for command in commands:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(_workspace_root()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        combined = "\n".join(part for part in (stdout, stderr) if part)
        outputs.append(f"$ {' '.join(command)}\n{combined or '[no output]'}")

        returncode = process.returncode if process.returncode is not None else 1

        if returncode != 0:
            success = False
            issues.extend(
                _state_summarise_cli_output(
                    command=command,
                    output=combined,
                    returncode=returncode,
                )
            )

    return success, issues, "\n\n".join(outputs)


def _state_summarise_cli_output(
    *,
    command: list[str],
    output: str,
    returncode: int,
) -> list[str]:
    """Convert CLI output into concise issue strings for retry routing."""
    command_name = " ".join(command[2:]) if len(command) > 2 else "CLI"
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return [f"{command_name} failed with exit code {returncode}."]

    issues = [f"{command_name} failed with exit code {returncode}."]
    issues.extend(f"{command_name}: {line}" for line in lines[:20])
    if len(lines) > 20:
        issues.append(f"{command_name}: ... {len(lines) - 20} more line(s) omitted")
    return issues


def _workspace_root() -> Path:
    """Return the repository root for CLI execution."""
    return Path(__file__).resolve().parents[3]


def _state_write_note(project_id: str, content: str) -> None:
    """
    Write an autopilot run Note to the graph.

    Silently skips the write when project_id is empty (test/standalone runs).

    Args:
        project_id: The project node to attach the Note to.
        content: The note body content.
    """
    if not project_id:
        return
    try:
        from datetime import datetime, timezone

        from ..db import db_get_connection
        from ..ids import id_generate_v7

        conn = db_get_connection()
        note_id = id_generate_v7()
        now = datetime.now(timezone.utc)

        conn.execute(
            """
            CREATE (n:Note {
                id: $id,
                content: $content,
                kind: 'autopilot',
                created_at: $ts
            })
            """,
            {"id": note_id, "content": content, "ts": now},
        )
        conn.execute(
            """
            MATCH (p:Project {id: $pid}), (n:Note {id: $nid})
            CREATE (p)-[:HAS_NOTE]->(n)
            """,
            {"pid": project_id, "nid": note_id},
        )
        logger.debug("Autopilot note %s written to graph.", note_id)
    except Exception as exc:
        logger.warning("Could not write autopilot note: %s", exc)


def _split_into_batches(items: list[str], concurrency: int) -> list[list[str]]:
    """
    Split a list of items into N roughly equal batches for parallel processing.

    Args:
        items: List of strings (e.g. file paths) to split.
        concurrency: Number of batches to create.

    Returns:
        List of lists, where each sub-list is a batch.
    """
    if concurrency <= 1 or not items:
        return [items] if items else []

    batch_size = (len(items) + concurrency - 1) // concurrency
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
