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

################
#   IMPORTS
################

import logging
import os
from dataclasses import dataclass, field

import anyio
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from ...config import AGENT_MODEL, DEFER_AGENT_MODEL_CHECK, config_model_settings
from ...resources.personas import MAPPER_PERSONA

################
#   CONSTANTS
################

_MAX_FILE_BYTES = 64_000

logger = logging.getLogger(__name__)


################
#   MODELS
################


class FeatureLocation(BaseModel):
    """
    A single feature-to-file mapping discovered during analysis.

    Represents the agent's understanding of where a named feature,
    subsystem, or concern lives in the codebase.
    """

    feature_name: str = Field(
        description="Human-readable name of the feature or concern, e.g. 'authentication', 'snapshot commit'."
    )
    primary_file: str = Field(
        description="File where this feature's core logic lives."
    )
    supporting_files: list[str] = Field(
        default_factory=list,
        description="Files that contribute to or support this feature.",
    )
    consumers: list[str] = Field(
        default_factory=list,
        description="Files that import or call into this feature.",
    )
    description: str = Field(
        description="One sentence describing what this feature does."
    )


class FileRelationship(BaseModel):
    """
    A directional dependency between two files.

    Represents an import, function call, or interface implementation
    that creates a coupling between source and target.
    """

    source_file: str = Field(description="File that depends on the target.")
    target_file: str = Field(description="File being depended upon.")
    relationship_kind: str = Field(
        description="Nature of the relationship: 'imports', 'calls', 'implements', 'embeds'."
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Specific symbols (functions, types) involved in the relationship.",
    )


class MapReport(BaseModel):
    """
    Complete codebase map produced by the map agent.

    Contains feature locations, file relationships, and a summary
    narrative. Written to the graph by the MCP tool wrapper.
    """

    package_path: str = Field(description="Root path that was mapped.")
    features: list[FeatureLocation] = Field(
        default_factory=list,
        description="Feature geography — what lives where.",
    )
    relationships: list[FileRelationship] = Field(
        default_factory=list,
        description="File-level dependency relationships.",
    )
    entry_points: list[str] = Field(
        default_factory=list,
        description="Files identified as top-level entry points (main, handlers, routers).",
    )
    summary: str = Field(
        description="Narrative overview of the codebase structure and key observations."
    )
    partial_failure: bool = Field(default=False)


################
#   DEPS
################


@dataclass
class MapDependencies:
    """
    Injectable dependencies for the map agent.

    Pass domain hints to guide feature identification — e.g. known
    subsystem names for the lakehouse agent variant.
    """

    package_path: str
    file_extension: str = ".py"
    known_features: list[str] = field(default_factory=list)
    skills_content: str = ""
    extra_file_context: str = ""

################
#   AGENT
################

map_agent: Agent[MapDependencies, MapReport] = Agent(
    AGENT_MODEL,
    deps_type=MapDependencies,
    output_type=MapReport,
    model_settings=config_model_settings(
        temperature=MAPPER_PERSONA.params.temperature,
        top_p=MAPPER_PERSONA.params.top_p,
    ),
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


################
#   PROMPTS
################


@map_agent.system_prompt
async def build_system_prompt(ctx: RunContext[MapDependencies]) -> str:
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


@map_agent.tool
async def list_files(ctx: RunContext[MapDependencies]) -> list[str]:
    """
    List all source files in the package directory.

    Walks the package path recursively and returns paths matching
    the configured file extension.
    """
    import glob

    pattern = os.path.join(ctx.deps.package_path, f"**/*{ctx.deps.file_extension}")
    return glob.glob(pattern, recursive=True)


@map_agent.tool
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
    state_dict = _get_state(ctx)
    state_dict["features"].extend(features)
    state_dict["relationships"].extend(relationships)

    results = []
    for path in file_paths[:5]:  # hard cap
        content = await _read_file_internal(path)
        results.append(f"### {path}\n{content}")

    if not results:
        return "No files requested. Findings stored."

    return "\n\n".join(results)


async def _read_file_internal(file_path: str) -> str:
    """Internal helper to read file content robustly."""
    if not os.path.exists(file_path):
        return f"ERROR:NOT_FOUND:{file_path}"

    try:
        raw = await anyio.Path(file_path).read_bytes()
    except Exception as exc:
        return f"ERROR:READ_FAILED:{exc}"

    if len(raw) > _MAX_FILE_BYTES:
        truncated = raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
        return truncated + f"\n\n[TRUNCATED — file exceeds {_MAX_FILE_BYTES} bytes]"

    return raw.decode("utf-8", errors="replace")


@map_agent.tool
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
    Retrieve or initialise the per-run accumulator dict.

    Stores features and relationships across tool calls within
    a single agent run.
    """
    if not hasattr(ctx, "_map_state"):
        ctx._map_state = {"features": [], "relationships": []}  # type: ignore[attr-defined]
    return ctx._map_state  # type: ignore[attr-defined]