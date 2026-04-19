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
from pathlib import Path
from typing import Any, Awaitable, Callable

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
    failed: bool = Field(
        default=False, description="True if sub-agent failed this batch."
    )
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
    batch_results: list[BatchResult] = field(default_factory=list)
    aggregate: dict[str, Any] = field(default_factory=dict)


SubagentRunner = Callable[
    [OrchestratorDependencies, list[BatchFileContent]],
    Awaitable[Any],
]

SUBAGENT_REGISTRY: dict[str, SubagentRunner] = {}


def register_subagent(name: str, runner: SubagentRunner) -> None:
    """Register a batched sub-agent runner for deterministic orchestration."""
    SUBAGENT_REGISTRY[name] = runner


################
#   AGENT
################

orchestrator_agent = Agent(
    AGENT_MODEL,
    name="orchestrator",
    deps_type=OrchestratorDependencies,
    output_type=OrchestratorReport,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


################
#   PROMPTS
################


@orchestrator_agent.system_prompt
def build_system_prompt(ctx: RunContext[OrchestratorDependencies]) -> str:
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
def list_files(ctx: RunContext[OrchestratorDependencies]) -> list[str]:
    """
    List all source files in the package directory.

    Returns paths matching the configured extension, sorted for
    deterministic batch ordering across runs.
    """
    return list_source_files(ctx.deps.package_path, ctx.deps.file_extension)


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
    capped_paths = file_paths[: ctx.deps.batch_size]
    batch_index = len(ctx.deps.batch_results)

    logger.info(
        "[ORCH] starting batch=%d subagent=%s files=%d",
        batch_index,
        ctx.deps.subagent_name,
        len(capped_paths),
    )

    file_contents = await _read_batch(capped_paths)
    result = await _invoke_subagent(ctx, batch_index, file_contents)

    ctx.deps.batch_results.append(result)
    _merge_into_aggregate(ctx.deps.aggregate, result, ctx.deps.subagent_name)

    status = "FAILED" if result.failed else f"{len(capped_paths)} files processed"
    finding_summary = _summarise_batch_result(result, ctx.deps.subagent_name)

    logger.info(
        "[ORCH] finished batch=%d subagent=%s failed=%s summary=%s",
        batch_index,
        ctx.deps.subagent_name,
        result.failed,
        finding_summary,
    )

    return f"Batch {batch_index}: {status}. {finding_summary}"


@orchestrator_agent.tool
def finalize(
    ctx: RunContext[OrchestratorDependencies],
    summary: str,
) -> OrchestratorReport:
    """
    Produce the final aggregated OrchestratorReport.

    Called exactly once after all batches have been processed.
    Computes run statistics from accumulated batch results.
    """
    batch_results = ctx.deps.batch_results
    failed = sum(1 for r in batch_results if r.failed)
    total_files = sum(len(r.files_processed) for r in batch_results)

    logger.info(
        "[ORCH] finalize subagent=%s total_batches=%d failed_batches=%d total_files=%d",
        ctx.deps.subagent_name,
        len(batch_results),
        failed,
        total_files,
    )

    return OrchestratorReport(
        package_path=ctx.deps.package_path,
        subagent_name=ctx.deps.subagent_name,
        total_files=total_files,
        total_batches=len(batch_results),
        failed_batches=failed,
        batch_results=batch_results,
        aggregate=ctx.deps.aggregate,
        summary=summary,
        partial_failure=failed > 0,
    )


################
#   SUBAGENT DISPATCH
################


async def run_orchestrator_batches(
    deps: OrchestratorDependencies,
    *,
    summary: str | None = None,
    progress_callback: Callable[[int, int, BatchResult], Awaitable[None]] | None = None,
) -> OrchestratorReport:
    """
    Run the full batched orchestration workflow deterministically.

    Python owns file discovery, batch ordering, sub-agent dispatch, aggregation,
    and final report construction. The LLM sub-agents only reason over the
    pre-read batch content they receive.
    """
    deps.batch_results.clear()
    deps.aggregate.clear()

    files = list_source_files(deps.package_path, deps.file_extension)
    batches = _split_batches(files, deps.batch_size)

    for batch_index, batch_paths in enumerate(batches):
        logger.info(
            "[ORCH] deterministic batch=%d/%d subagent=%s files=%d",
            batch_index + 1,
            len(batches),
            deps.subagent_name,
            len(batch_paths),
        )
        file_contents = await _read_batch(batch_paths)
        result = await _invoke_subagent(deps, batch_index, file_contents)
        deps.batch_results.append(result)
        _merge_into_aggregate(deps.aggregate, result, deps.subagent_name)
        if progress_callback is not None:
            await progress_callback(batch_index + 1, len(batches), result)

    failed = sum(1 for r in deps.batch_results if r.failed)
    total_files = sum(len(r.files_processed) for r in deps.batch_results)
    final_summary = summary or _summarise_orchestration(
        deps.subagent_name,
        total_files,
        len(deps.batch_results),
        failed,
        deps.aggregate,
    )
    return OrchestratorReport(
        package_path=deps.package_path,
        subagent_name=deps.subagent_name,
        total_files=total_files,
        total_batches=len(deps.batch_results),
        failed_batches=failed,
        batch_results=list(deps.batch_results),
        aggregate=dict(deps.aggregate),
        summary=final_summary,
        partial_failure=failed > 0,
    )


async def _invoke_subagent(
    deps: OrchestratorDependencies | RunContext[OrchestratorDependencies],
    batch_index: int,
    file_contents: list[BatchFileContent],
) -> BatchResult:
    """
    Dispatch a batch to the appropriate sub-agent.

    Routes to audit, map, or decision agent based on subagent_name.
    Runs with a timeout and catches failures to allow partial runs.
    """
    if isinstance(deps, RunContext):
        deps = deps.deps
    paths = [f.path for f in file_contents]

    try:
        with anyio.fail_after(deps.timeout):
            output = await _dispatch(deps, file_contents)

        return BatchResult(
            batch_index=batch_index,
            files_processed=paths,
            output=output,
        )

    except TimeoutError:
        logger.warning("Batch %d timed out after %.0fs", batch_index, deps.timeout)
        return BatchResult(
            batch_index=batch_index,
            files_processed=paths,
            output=None,
            failed=True,
            error=f"Timeout after {deps.timeout}s",
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
    deps: OrchestratorDependencies | RunContext[OrchestratorDependencies],
    file_contents: list[BatchFileContent],
) -> Any:
    """
    Route to the correct sub-agent based on subagent_name.

    Builds sub-agent deps with the pre-read file content injected
    so sub-agents do not need to re-read files from disk.
    """
    if isinstance(deps, RunContext):
        deps = deps.deps
    name = deps.subagent_name
    runner = SUBAGENT_REGISTRY.get(name)
    if runner is not None:
        return await runner(deps, file_contents)
    project_helper = _find_project_helper_runner(deps, name)
    if project_helper is not None:
        return project_helper

    supported = ", ".join(sorted(SUBAGENT_REGISTRY)) or "<none>"
    raise ValueError(f"Unknown sub-agent: '{name}'. Supported: {supported}.")


def _find_project_helper_runner(
    deps: OrchestratorDependencies,
    name: str,
) -> dict[str, Any] | None:
    """
    Resolve a project-specific helper-agent spec for orchestration.

    Helper specs are structured YAML, not arbitrary executable Python. Returning
    the validated spec lets callers see that the helper was discovered while
    keeping execution gated until a concrete runtime is attached.
    """
    try:
        from .builder.agent_builder import find_helper_agent_spec

        project_root = str(deps.extra_context.get("project_root") or deps.package_path)
        spec = find_helper_agent_spec(project_root, deps.project_id, name)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not resolve project helper spec %s: %s", name, exc)
        return None

    if spec is None:
        return None
    return {
        "helper_agent": spec.model_dump(mode="json"),
        "status": "spec_discovered",
        "message": (
            "Project helper-agent spec found. Runtime execution is pending "
            "a concrete helper-agent adapter."
        ),
    }


async def _run_audit_batch(
    deps: OrchestratorDependencies,
    file_contents: list[BatchFileContent],
) -> Any:
    """
    Run the audit agent on a batch of pre-read files.

    Injects file content via skills_content so the agent has all
    files available without additional read tool calls.
    """
    return await _run_audit_rule_set_batch(deps, file_contents, "default")


async def _run_audit_rule_set_batch(
    deps: OrchestratorDependencies,
    file_contents: list[BatchFileContent],
    rule_set: str,
) -> Any:
    """Run a preloaded audit batch with a named audit rule set."""
    from .audit.factory import build_audit_agent_bundle

    file_block = _format_file_block(file_contents)
    bundle = build_audit_agent_bundle(
        package_path=deps.package_path,
        rule_set=rule_set,
        tool_mode="preloaded",
        file_extension=deps.file_extension,
        skills_content=deps.skills_content,
        extra_file_context=file_block,
    )
    prompt = (
        f"Analyse these {len(file_contents)} files against the rules checklist. "
        "The file contents are provided in extra_file_context. Return an AuditReport."
    )
    result = await bundle.agent.run(prompt, deps=bundle.deps)
    return result.output


async def _run_security_audit_batch(
    deps: OrchestratorDependencies,
    file_contents: list[BatchFileContent],
) -> Any:
    """Run security-focused preloaded audit."""
    return await _run_audit_rule_set_batch(deps, file_contents, "security")


async def _run_bug_audit_batch(
    deps: OrchestratorDependencies,
    file_contents: list[BatchFileContent],
) -> Any:
    """Run correctness/bug-focused preloaded audit."""
    return await _run_audit_rule_set_batch(deps, file_contents, "bug")


async def _run_smell_audit_batch(
    deps: OrchestratorDependencies,
    file_contents: list[BatchFileContent],
) -> Any:
    """Run maintainability/code-smell-focused preloaded audit."""
    return await _run_audit_rule_set_batch(deps, file_contents, "smell")


async def _run_map_batch(
    deps: OrchestratorDependencies,
    file_contents: list[BatchFileContent],
) -> Any:
    """
    Run the map agent on a batch of pre-read files.

    Injects file content so the map agent can identify features and
    relationships without separate file reads.
    """
    from .map.map_agent import MapDependencies, map_agent

    file_block = _format_file_block(file_contents)
    map_deps = MapDependencies(
        package_path=deps.package_path,
        file_extension=deps.file_extension,
        skills_content=deps.skills_content,
        known_features=deps.extra_context.get("known_features", []),
        extra_file_context=file_block,
    )
    prompt = (
        f"Map features and relationships in these {len(file_contents)} files. "
        "File contents are in extra_file_context — do not call read_file. "
        "Record each feature and relationship then finalize."
    )
    result = await map_agent.run(prompt, deps=map_deps)
    return result.output


async def _run_decision_batch(
    deps: OrchestratorDependencies,
    file_contents: list[BatchFileContent],
) -> Any:
    """
    Run the decision review agent on a batch of pre-read files.

    Passes pre-read content and injects decisions from extra_context.
    """
    from .document.decision_agent import DecisionDependencies, decision_agent

    file_block = _format_file_block(file_contents)
    decision_deps = DecisionDependencies(
        project_id=deps.project_id,
        package_path=deps.package_path,
        decisions=deps.extra_context.get("decisions", []),
        skills_content=deps.skills_content,
        extra_file_context=file_block,
    )
    prompt = (
        f"Review decisions against these {len(file_contents)} files. "
        "File contents are in extra_file_context — do not call read_file. "
        "Record each review then finalize."
    )
    result = await decision_agent.run(prompt, deps=decision_deps)
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
            aggregate["all_findings"].extend([f.model_dump() for f in fr.findings])
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
        aggregate["relationships"].extend(
            [r.model_dump() for r in output.relationships]
        )
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
        await anyio.sleep(0)
        results[index] = _read_single(path)

    async with anyio.create_task_group() as tg:
        for i, path in enumerate(paths):
            tg.start_soon(read_one, i, path)

    return [r for r in results if r is not None]


def _read_single(path: str) -> BatchFileContent:
    """
    Read a single file and return a BatchFileContent.

    Truncates to _MAX_FILE_BYTES and flags the truncation.
    Returns error content if the file cannot be read.
    """
    if not os.path.exists(path):
        return BatchFileContent(
            path=path, content="ERROR: file not found", truncated=False
        )

    try:
        raw = Path(path).read_bytes()
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


def list_source_files(package_path: str, file_extension: str) -> list[str]:
    """List source files matching an extension in deterministic order."""
    import glob

    pattern = os.path.join(package_path, f"**/*{file_extension}")
    return sorted(glob.glob(pattern, recursive=True))


def _split_batches(paths: list[str], batch_size: int) -> list[list[str]]:
    """Split paths into non-empty bounded batches."""
    safe_batch_size = max(1, batch_size)
    return [
        paths[index : index + safe_batch_size]
        for index in range(0, len(paths), safe_batch_size)
    ]


def _summarise_orchestration(
    subagent_name: str,
    total_files: int,
    total_batches: int,
    failed_batches: int,
    aggregate: dict[str, Any],
) -> str:
    """Build a deterministic final summary for a batch orchestration run."""
    status = "partial" if failed_batches else "completed"
    details = ""
    if subagent_name == "audit":
        details = f" findings={len(aggregate.get('all_findings', []))}"
    elif subagent_name == "map":
        details = (
            f" features={len(aggregate.get('features', []))}"
            f" relationships={len(aggregate.get('relationships', []))}"
        )
    elif subagent_name == "decision":
        details = f" reviews={len(aggregate.get('reviews', []))}"
    return (
        f"{status}: {subagent_name} processed {total_files} file(s) "
        f"across {total_batches} batch(es); failed_batches={failed_batches}.{details}"
    )


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


register_subagent("audit", _run_audit_batch)
register_subagent("security_audit", _run_security_audit_batch)
register_subagent("bug_audit", _run_bug_audit_batch)
register_subagent("smell_audit", _run_smell_audit_batch)
register_subagent("map", _run_map_batch)
register_subagent("decision", _run_decision_batch)
