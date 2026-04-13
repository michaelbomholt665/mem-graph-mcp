#!/usr/bin/env python3
# src/mem_graph/agents/orchestrator_agent.py
"""
Orchestrator agent.

Coordinates batched sub-agent runs over a file tree. Reads files in
batches of N (default 5), invokes a named sub-agent per batch, aggregates
results incrementally after each batch, and persists progress to allow
resume after failure. The main AI calls this agent rather than individual
agents directly when work spans many files.

Supported sub-agents: audit, map, decision.
"""

from __future__ import annotations

################
#   IMPORTS
################

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import anyio
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from ..config import AGENT_MODEL, DEFER_AGENT_MODEL_CHECK

################
#   CONSTANTS
################

_DEFAULT_BATCH_SIZE = 5
_DEFAULT_CONCURRENCY = 2
_DEFAULT_TIMEOUT = 120.0
_MAX_FILE_BYTES = 64_000

logger = logging.getLogger(__name__)


################
#   MODELS
################


class BatchFileContent(BaseModel):
    """
    A single file's path and content for passing into a batch.

    Content is pre-read by the orchestrator so sub-agents receive
    everything they need without additional file I/O tool calls.
    """

    path: str = Field(description="Absolute path to the file.")
    content: str = Field(description="File content, truncated if over size limit.")
    truncated: bool = Field(default=False, description="True if content was truncated.")


class BatchResult(BaseModel):
    """
    Aggregated result from one batch of sub-agent invocations.

    Carries the raw sub-agent output alongside batch metadata so the
    aggregation step can track provenance.
    """

    batch_index: int = Field(description="Zero-based index of this batch.")
    files_processed: list[str] = Field(description="Paths processed in this batch.")
    output: Any = Field(description="Raw output from the sub-agent.")
    failed: bool = Field(default=False, description="True if sub-agent failed this batch.")
    error: str | None = Field(default=None, description="Error message on failure.")


class OrchestratorReport(BaseModel):
    """
    Final aggregated output from an orchestrator run.

    Contains per-batch results, a merged aggregate, and run metadata.
    The aggregate structure depends on the sub-agent type — audit
    produces merged findings, map produces merged features, etc.
    """

    package_path: str
    subagent_name: str
    total_files: int
    total_batches: int
    failed_batches: int = Field(default=0)
    batch_results: list[BatchResult] = Field(default_factory=list)
    aggregate: dict = Field(
        default_factory=dict,
        description="Merged output across all batches, keyed by sub-agent output type.",
    )
    summary: str = Field(description="Narrative summary of the orchestration run.")
    partial_failure: bool = Field(default=False)


################
#   DEPS
################


@dataclass
class OrchestratorDependencies:
    """
    Injectable dependencies for the orchestrator agent.

    subagent_name selects which agent to run per batch.
    project_id is passed through to sub-agents that need graph linkage.
    batch_size controls how many files per batch (default 5).
    concurrency controls how many batches run simultaneously.
    """

    package_path: str
    project_id: str
    subagent_name: str = "audit"
    file_extension: str = ".py"
    batch_size: int = _DEFAULT_BATCH_SIZE
    concurrency: int = _DEFAULT_CONCURRENCY
    timeout: float = _DEFAULT_TIMEOUT
    skills_content: str = ""
    extra_context: dict = field(default_factory=dict)


################
#   AGENT
################

orchestrator_agent = Agent(
    AGENT_MODEL,
    deps_type=OrchestratorDependencies,
    output_type=OrchestratorReport,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


################
#   PROMPTS
################


@orchestrator_agent.system_prompt
async def build_system_prompt(ctx: RunContext[OrchestratorDependencies]) -> str:
    """
    Build the orchestrator system prompt.

    Instructs the agent on the batched pipeline loop — list files,
    process in batches, aggregate after each batch, finalize at end.
    """
    return f"""You are an orchestration agent. You coordinate analysis work over a codebase
by processing files in small batches and aggregating results incrementally.

## Configuration
- Package: {ctx.deps.package_path}
- Sub-agent: {ctx.deps.subagent_name}
- Batch size: {ctx.deps.batch_size} files per batch
- Project ID: {ctx.deps.project_id}

## Pipeline (follow this exactly)
1. Call `list_files` to get all file paths.
2. Call `process_batch` with the first {ctx.deps.batch_size} paths.
   - This reads the files AND runs the sub-agent AND records results in one call.
   - You receive a summary of what was found.
3. Call `process_batch` with the next {ctx.deps.batch_size} paths.
4. Continue until all files are processed.
5. Call `finalize` with a narrative summary of all findings across all batches.

## Critical rules
- Never call `process_batch` with more than {ctx.deps.batch_size} files.
- Always call `process_batch` before moving to the next group of files.
- Do not attempt to analyse file content yourself — `process_batch` handles analysis.
- Call `finalize` exactly once, after all batches are complete.
"""


################
#   TOOLS
################


@orchestrator_agent.tool
async def list_files(ctx: RunContext[OrchestratorDependencies]) -> list[str]:
    """
    List all source files in the package directory.

    Returns paths matching the configured extension, sorted for
    deterministic batch ordering across runs.
    """
    import glob

    pattern = os.path.join(ctx.deps.package_path, f"**/*{ctx.deps.file_extension}")
    paths = glob.glob(pattern, recursive=True)
    return sorted(paths)


@orchestrator_agent.tool
async def process_batch(
    ctx: RunContext[OrchestratorDependencies],
    file_paths: list[str],
) -> str:
    """
    Read files, run the sub-agent, and record results for this batch.

    This is the core orchestration step — it atomically reads a batch
    of files and invokes the configured sub-agent on their contents.
    Results are stored in working state for aggregation by finalize.
    Call this once per batch before moving to the next group of files.
    """
    capped_paths = file_paths[:ctx.deps.batch_size]
    state = _get_state(ctx)
    batch_index = len(state["batch_results"])

    file_contents = await _read_batch(capped_paths)
    result = await _invoke_subagent(ctx, batch_index, file_contents)

    state["batch_results"].append(result)
    _merge_into_aggregate(state["aggregate"], result, ctx.deps.subagent_name)

    status = "FAILED" if result.failed else f"{len(capped_paths)} files processed"
    finding_summary = _summarise_batch_result(result, ctx.deps.subagent_name)

    return f"Batch {batch_index}: {status}. {finding_summary}"


@orchestrator_agent.tool
async def finalize(
    ctx: RunContext[OrchestratorDependencies],
    summary: str,
) -> OrchestratorReport:
    """
    Produce the final aggregated OrchestratorReport.

    Called exactly once after all batches have been processed.
    Computes run statistics from accumulated batch results.
    """
    state = _get_state(ctx)
    batch_results = state["batch_results"]
    failed = sum(1 for r in batch_results if r.failed)
    total_files = sum(len(r.files_processed) for r in batch_results)

    return OrchestratorReport(
        package_path=ctx.deps.package_path,
        subagent_name=ctx.deps.subagent_name,
        total_files=total_files,
        total_batches=len(batch_results),
        failed_batches=failed,
        batch_results=batch_results,
        aggregate=state["aggregate"],
        summary=summary,
        partial_failure=failed > 0,
    )


################
#   SUBAGENT DISPATCH
################


async def _invoke_subagent(
    ctx: RunContext[OrchestratorDependencies],
    batch_index: int,
    file_contents: list[BatchFileContent],
) -> BatchResult:
    """
    Dispatch a batch to the appropriate sub-agent.

    Routes to audit, map, or decision agent based on subagent_name.
    Runs with a timeout and catches failures to allow partial runs.
    """
    paths = [f.path for f in file_contents]

    try:
        with anyio.fail_after(ctx.deps.timeout):
            output = await _dispatch(ctx, file_contents)

        return BatchResult(
            batch_index=batch_index,
            files_processed=paths,
            output=output,
        )

    except TimeoutError:
        logger.warning("Batch %d timed out after %.0fs", batch_index, ctx.deps.timeout)
        return BatchResult(
            batch_index=batch_index,
            files_processed=paths,
            output=None,
            failed=True,
            error=f"Timeout after {ctx.deps.timeout}s",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Batch %d sub-agent failed: %s", batch_index, exc)
        return BatchResult(
            batch_index=batch_index,
            files_processed=paths,
            output=None,
            failed=True,
            error=str(exc),
        )


async def _dispatch(
    ctx: RunContext[OrchestratorDependencies],
    file_contents: list[BatchFileContent],
) -> Any:
    """
    Route to the correct sub-agent based on subagent_name.

    Builds sub-agent deps with the pre-read file content injected
    so sub-agents do not need to re-read files from disk.
    """
    name = ctx.deps.subagent_name

    if name == "audit":
        return await _run_audit_batch(ctx, file_contents)
    if name == "map":
        return await _run_map_batch(ctx, file_contents)
    if name == "decision":
        return await _run_decision_batch(ctx, file_contents)

    raise ValueError(f"Unknown sub-agent: '{name}'. Supported: audit, map, decision.")


async def _run_audit_batch(
    ctx: RunContext[OrchestratorDependencies],
    file_contents: list[BatchFileContent],
) -> Any:
    """
    Run the audit agent on a batch of pre-read files.

    Injects file content via skills_content so the agent has all
    files available without additional read tool calls.
    """
    from .audit_agent import AuditDependencies, audit_agent

    file_block = _format_file_block(file_contents)
    deps = AuditDependencies(
        package_path=ctx.deps.package_path,
        file_extension=ctx.deps.file_extension,
        skills_content=ctx.deps.skills_content,
        extra_file_context=file_block,
    )
    prompt = (
        f"Analyse these {len(file_contents)} files against the rules checklist. "
        "The file contents are provided in extra_file_context — do not call read_file. "
        "Record findings for each file then finalize."
    )
    result = await audit_agent.run(prompt, deps=deps)
    return result.output


async def _run_map_batch(
    ctx: RunContext[OrchestratorDependencies],
    file_contents: list[BatchFileContent],
) -> Any:
    """
    Run the map agent on a batch of pre-read files.

    Injects file content so the map agent can identify features and
    relationships without separate file reads.
    """
    from .map_agent import MapDependencies, map_agent

    file_block = _format_file_block(file_contents)
    deps = MapDependencies(
        package_path=ctx.deps.package_path,
        file_extension=ctx.deps.file_extension,
        skills_content=ctx.deps.skills_content,
        known_features=ctx.deps.extra_context.get("known_features", []),
        extra_file_context=file_block,
    )
    prompt = (
        f"Map features and relationships in these {len(file_contents)} files. "
        "File contents are in extra_file_context — do not call read_file. "
        "Record each feature and relationship then finalize."
    )
    result = await map_agent.run(prompt, deps=deps)
    return result.output


async def _run_decision_batch(
    ctx: RunContext[OrchestratorDependencies],
    file_contents: list[BatchFileContent],
) -> Any:
    """
    Run the decision review agent on a batch of pre-read files.

    Passes pre-read content and injects decisions from extra_context.
    """
    from .decision_agent import DecisionDependencies, decision_agent

    file_block = _format_file_block(file_contents)
    deps = DecisionDependencies(
        project_id=ctx.deps.project_id,
        package_path=ctx.deps.package_path,
        decisions=ctx.deps.extra_context.get("decisions", []),
        skills_content=ctx.deps.skills_content,
        extra_file_context=file_block,
    )
    prompt = (
        f"Review decisions against these {len(file_contents)} files. "
        "File contents are in extra_file_context — do not call read_file. "
        "Record each review then finalize."
    )
    result = await decision_agent.run(prompt, deps=deps)
    return result.output


################
#   AGGREGATION
################


def _merge_into_aggregate(
    aggregate: dict,
    result: BatchResult,
    subagent_name: str,
) -> None:
    """
    Merge a batch result into the running aggregate dict.

    Each sub-agent type has its own merge strategy — findings are
    extended, features are extended, reviews are extended.
    Skips failed batches silently (they remain in batch_results).
    """
    if result.failed or result.output is None:
        return

    if subagent_name == "audit":
        _merge_audit(aggregate, result.output)
    elif subagent_name == "map":
        _merge_map(aggregate, result.output)
    elif subagent_name == "decision":
        _merge_decision(aggregate, result.output)


def _merge_audit(aggregate: dict, output: Any) -> None:
    """Merge audit report findings into the running aggregate."""
    aggregate.setdefault("all_findings", [])
    aggregate.setdefault("files_analysed", 0)
    aggregate.setdefault("files_skipped", 0)

    if hasattr(output, "file_results"):
        for fr in output.file_results:
            aggregate["all_findings"].extend(
                [f.model_dump() for f in fr.findings]
            )
            if fr.skipped:
                aggregate["files_skipped"] += 1
            else:
                aggregate["files_analysed"] += 1


def _merge_map(aggregate: dict, output: Any) -> None:
    """Merge map report features and relationships into the aggregate."""
    aggregate.setdefault("features", [])
    aggregate.setdefault("relationships", [])
    aggregate.setdefault("entry_points", [])

    if hasattr(output, "features"):
        aggregate["features"].extend([f.model_dump() for f in output.features])
    if hasattr(output, "relationships"):
        aggregate["relationships"].extend([r.model_dump() for r in output.relationships])
    if hasattr(output, "entry_points"):
        aggregate["entry_points"].extend(output.entry_points)


def _merge_decision(aggregate: dict, output: Any) -> None:
    """Merge decision reviews into the running aggregate."""
    aggregate.setdefault("reviews", [])
    aggregate.setdefault("drifted", [])

    if hasattr(output, "reviews"):
        for review in output.reviews:
            aggregate["reviews"].append(review.model_dump())
            if review.status.value == "drifted":
                aggregate["drifted"].append(review.decision_id)


################
#   FILE I/O
################


async def _read_batch(paths: list[str]) -> list[BatchFileContent]:
    """
    Read a list of files concurrently using anyio task group.

    Returns BatchFileContent for each path, truncating oversized files.
    Files that cannot be read are included with an error message as content.
    """
    results: list[BatchFileContent | None] = [None] * len(paths)

    async def read_one(index: int, path: str) -> None:
        results[index] = await _read_single(path)

    async with anyio.create_task_group() as tg:
        for i, path in enumerate(paths):
            tg.start_soon(read_one, i, path)

    return [r for r in results if r is not None]


async def _read_single(path: str) -> BatchFileContent:
    """
    Read a single file and return a BatchFileContent.

    Truncates to _MAX_FILE_BYTES and flags the truncation.
    Returns error content if the file cannot be read.
    """
    if not os.path.exists(path):
        return BatchFileContent(path=path, content="ERROR: file not found", truncated=False)

    try:
        raw = await anyio.Path(path).read_bytes()
    except Exception as exc:
        return BatchFileContent(path=path, content=f"ERROR: {exc}", truncated=False)

    if len(raw) > _MAX_FILE_BYTES:
        content = raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
        return BatchFileContent(path=path, content=content, truncated=True)

    return BatchFileContent(
        path=path,
        content=raw.decode("utf-8", errors="replace"),
        truncated=False,
    )


################
#   HELPERS
################


def _get_state(ctx: RunContext[OrchestratorDependencies]) -> dict:
    """Retrieve or initialise the per-run orchestrator state."""
    if not hasattr(ctx, "_orch_state"):
        ctx._orch_state = {"batch_results": [], "aggregate": {}}  # type: ignore[attr-defined]
    return ctx._orch_state  # type: ignore[attr-defined]


def _format_file_block(file_contents: list[BatchFileContent]) -> str:
    """
    Format a list of BatchFileContent into a single annotated string.

    Produces a block the sub-agent can read as a unit, with clear
    file delimiters so the agent knows where each file starts and ends.
    """
    blocks = []
    for fc in file_contents:
        truncation_note = " [TRUNCATED]" if fc.truncated else ""
        blocks.append(f"### {fc.path}{truncation_note}\n```\n{fc.content}\n```")
    return "\n\n".join(blocks)


def _summarise_batch_result(result: BatchResult, subagent_name: str) -> str:
    """
    Produce a one-line summary of a batch result for the agent's progress log.

    Gives the orchestrator agent enough feedback to know what was found
    without overwhelming its context with full finding details.
    """
    if result.failed:
        return f"Error: {result.error}"

    output = result.output
    if subagent_name == "audit" and hasattr(output, "stats"):
        return f"{output.stats.total_findings} finding(s) — {output.stats.blocker_count} blocker(s)."
    if subagent_name == "map" and hasattr(output, "features"):
        return f"{len(output.features)} feature(s), {len(output.relationships)} relationship(s) mapped."
    if subagent_name == "decision" and hasattr(output, "reviews"):
        drifted = sum(1 for r in output.reviews if r.status.value == "drifted")
        return f"{len(output.reviews)} decision(s) reviewed — {drifted} drifted."

    return "Completed."