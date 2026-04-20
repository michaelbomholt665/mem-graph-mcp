#!/usr/bin/env python3
# src/mem_graph/agents/map/map_agent.py
"""
Codebase context map agent.

Builds a feature geography map of a codebase — what features live in
which files, what calls what, and what the blast radius of touching a
given file is. Writes relationships to the mem-graph graph rather than
producing a full AST. Designed to be queried by other agents (task
decomposition, decision review) to provide codebase context.
"""

from __future__ import annotations

import logging
import os

################
#   IMPORTS
################
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import Agent, RunContext

from ...capabilities import ReasoningStrategyCapability
from ...config import AGENT_MODEL, DEFER_AGENT_MODEL_CHECK, config_model_settings
from ...models.agent_outputs import FeatureLocation, FileRelationship, MapReport
from ...resources.personas import MAPPER_PERSONA
from ..tooling import hide_tool_in_preloaded_mode, require_max_items

################
#   CONSTANTS
################

_MAX_FILE_BYTES = 64_000

logger = logging.getLogger(__name__)


################
#   DEPS
################


@dataclass
class MapDependencies:
    """
    Injectable dependencies for the map agent.

    Pass domain hints to guide feature identification — e.g. known
    subsystem names for the lakehouse agent variant.

    _map_features and _map_relationships accumulate identified features
    and relationships across tool calls; never monkey-patched onto RunContext.
    """

    package_path: str
    file_extension: str = ".py"
    known_features: list[str] = field(default_factory=list)
    skills_content: str = ""
    extra_file_context: str = ""
    _map_features: list[FeatureLocation] = field(default_factory=list)
    _map_relationships: list[FileRelationship] = field(default_factory=list)
    reasoning_mode: str = ""


################
#   AGENT
################

map_agent: Agent[MapDependencies, MapReport] = Agent(
    AGENT_MODEL,
    name="map-codebase",
    deps_type=MapDependencies,
    output_type=MapReport,
    model_settings=config_model_settings(
        temperature=MAPPER_PERSONA.params.temperature,
        top_p=MAPPER_PERSONA.params.top_p,
    ),
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
    capabilities=[ReasoningStrategyCapability()],
)


################
#   PROMPTS
################


@map_agent.instructions
async def build_instructions(ctx: RunContext[MapDependencies]) -> str:
    """
    Build the system prompt from deps and the Mapper persona at runtime.
    """
    persona_instr = MAPPER_PERSONA.get_system_instructions()
    skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."
    known_block = (
        "Known subsystems to look for: " + ", ".join(ctx.deps.known_features)
        if ctx.deps.known_features
        else "No known subsystems provided — discover features from the code."
    )

    if ctx.deps.extra_file_context:
        file_section = (
            "## Pre-loaded Files\n"
            f"{ctx.deps.extra_file_context}\n\n"
            "The files above were pre-loaded by the orchestrator."
        )
        workflow = """1. Analyse only the pre-loaded files shown above.
2. Identify features, relationships, and likely entry points from those files.
3. Return the final MapReport directly as structured output.
4. Do not call list_files, process_batch, or finalize_map."""
        analysis_scope = "the pre-loaded files"
    else:
        file_section = ""
        workflow = """1. Call `list_files` to discover the structure.
2. Call `process_batch` iteratively. Pass up to 5 `file_paths` to read, along with `features` and `relationships` identified from the previous batch.
3. Assess the returned file content. Identify feature ownership and file dependency relationships.
4. Call `process_batch` again to submit your newly identified structures and request the next batch.
5. After all files are processed, call `process_batch` with an empty `file_paths` list to submit your final features and relationships.
6. Once mapped, call `finalize_map` with entry points and a summary narrative."""
        analysis_scope = f"all source files in {ctx.deps.package_path}"

    return f"""{persona_instr}

## Domain Knowledge
{skills_block}

{file_section}

## Known Subsystems
{known_block}

## Your Task
Analyse {analysis_scope}.

{workflow}

## What to Map
- Feature ownership: which file is the authoritative home for each concern
- Consumer relationships: what files call into or import from each other
- Entry points: handlers, routers, main packages, CLI commands
- Blast radius indicators: files imported by many others are high-blast-radius

## What NOT to Map
- Trivial utility imports (fmt, os, errors)
- Test files (note them but do not map their internal structure)
- Generated code (note it as generated, skip internal mapping)

Be precise about file paths. Use the exact paths returned by list_files.
"""


################
#   TOOLS
################


@map_agent.tool(prepare=hide_tool_in_preloaded_mode)  # Scope: agent-local only
async def list_files(ctx: RunContext[MapDependencies]) -> list[str]:
    """
    List all source files in the package directory.

    Walks the package path recursively and returns paths matching
    the configured file extension.
    """
    import glob

    pattern = os.path.join(ctx.deps.package_path, f"**/*{ctx.deps.file_extension}")
    return glob.glob(pattern, recursive=True)


@map_agent.tool(prepare=hide_tool_in_preloaded_mode)  # Scope: agent-local only
async def process_batch(
    ctx: RunContext[MapDependencies],
    file_paths: list[str],
    features: list[FeatureLocation],
    relationships: list[FileRelationship],
) -> str:
    """
    Submit features and relationships identified from the previous batch
    and receive the next batch of file content to read.

    Request at most 5 files at a time. Returns the content. If no more files,
    pass an empty list for file_paths to just submit the findings.
    """
    require_max_items("file_paths", file_paths, limit=5)
    state_dict = _get_state(ctx)
    state_dict["features"].extend(features)
    state_dict["relationships"].extend(relationships)

    results = []
    for path in file_paths:
        content = _read_file_internal(path)
        results.append(f"### {path}\n{content}")

    if not results:
        return "No files requested. Findings stored."

    return "\n\n".join(results)


def _read_file_internal(file_path: str) -> str:
    """Internal helper to read file content robustly."""
    if not os.path.exists(file_path):
        return f"ERROR:NOT_FOUND:{file_path}"

    try:
        raw = Path(file_path).read_bytes()
    except Exception as exc:
        return f"ERROR:READ_FAILED:{exc}"

    if len(raw) > _MAX_FILE_BYTES:
        truncated = raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
        return truncated + f"\n\n[TRUNCATED — file exceeds {_MAX_FILE_BYTES} bytes]"

    return raw.decode("utf-8", errors="replace")


@map_agent.tool(prepare=hide_tool_in_preloaded_mode)  # Scope: agent-local only
async def finalize_map(
    ctx: RunContext[MapDependencies],
    entry_points: list[str],
    summary: str,
    partial_failure: bool = False,
) -> MapReport:
    """
    Aggregate all recorded features and relationships into the final MapReport.

    Called once after all files have been processed and all features
    and relationships recorded.
    """
    state = _get_state(ctx)

    return MapReport(
        package_path=ctx.deps.package_path,
        features=state["features"],
        relationships=state["relationships"],
        entry_points=entry_points,
        summary=summary,
        partial_failure=partial_failure,
    )


################
#   HELPERS
################


def _get_state(ctx: RunContext[MapDependencies]) -> dict:
    """
    Return the per-run accumulator dict from deps.

    Uses deps._map_features and deps._map_relationships instead of
    monkey-patching onto RunContext.
    """
    return {
        "features": ctx.deps._map_features,
        "relationships": ctx.deps._map_relationships,
    }
