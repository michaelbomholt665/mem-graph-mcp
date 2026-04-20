#!/usr/bin/env python3
# src/mem_graph/agents/document/scribe_agent.py
"""
Scribe Agent — documentation and style enforcer.

The Stylist. Applies language-specific coding standards to proposed code
changes: file headers, module docstrings, function/class docstrings, and
naming conventions. Never touches functional logic — only style and docs.
"""

from __future__ import annotations

################
#   IMPORTS
################

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from ...capabilities import ReasoningStrategyCapability
from ...config import DEFER_AGENT_MODEL_CHECK, ModelTier, config_get_model_for_tier
from ...resources.coding_standards import coding_standards_get_for_language
from ...resources.personas import SCRIBE_PERSONA
from ...resources.prompts import build_tool_names_for_prompt

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

_SCRIBE_MODEL = config_get_model_for_tier(ModelTier.MICRO)

################
#   MODELS
################


class StyledFilePatch(BaseModel):
    """
    A style-corrected version of a proposed file patch.

    Attributes:
        file_path: Repo-relative path to the file being styled.
        original_content: File content before style correction.
        styled_content: File content after applying standards.
        changes_made: List of style changes applied.
    """

    file_path: str = Field(description="Repo-relative path to the target file.")
    original_content: str = Field(description="Content sent to the Scribe for styling.")
    styled_content: str = Field(description="Content after applying coding standards.")
    changes_made: list[str] = Field(
        default_factory=list,
        description="Short descriptions of each style change applied.",
    )


class ScribeReport(BaseModel):
    """
    Complete output from a Scribe Agent run.

    Contains all style-corrected file patches and a summary of all
    documentation changes made across the run.
    """

    styled_patches: list[StyledFilePatch] = Field(
        default_factory=list,
        description="Style-corrected file patches.",
    )
    summary: str = Field(description="Narrative summary of documentation improvements.")
    standards_applied: str = Field(description="Language standards block that was enforced.")


################
#   DEPS
################


@dataclass
class ScribeDependencies:
    """
    Injectable dependencies for the Scribe Agent.

    Attributes:
        language: Target language for standard selection (python, go, typescript).
        file_contents: File content to style-check, keyed by file path.
        architecture_guardrails: Optional guardrails block for naming conventions.
        skills_content: Optional SKILL.md content for extra guidance.
        _scribe_patches: Accumulated StyledFilePatch objects;
            never monkey-patched onto RunContext.
    """

    language: str
    file_contents: dict[str, str] = field(default_factory=dict)
    architecture_guardrails: str = ""
    skills_content: str = ""
    _scribe_patches: list[StyledFilePatch] = field(default_factory=list)
    reasoning_mode: str = ""


################
#   AGENT
################

scribe_agent: Agent[ScribeDependencies, ScribeReport] = Agent(
    _SCRIBE_MODEL,
    name="scribe",
    deps_type=ScribeDependencies,
    output_type=ScribeReport,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
    capabilities=[ReasoningStrategyCapability()],
)


@scribe_agent.instructions
async def scribe_build_instructions(ctx: RunContext[ScribeDependencies]) -> str:
    """
    Build the Scribe Agent system prompt.

    Injects the Stylist persona with the full coding standards block for
    the target language and a hard constraint against touching logic.

    Args:
        ctx: The run context with ScribeDependencies.

    Returns:
        Complete system prompt string.
    """
    standards = coding_standards_get_for_language(ctx.deps.language)

    tools_section = build_tool_names_for_prompt(
        ["scribe_read_file", "scribe_apply_standards"]
    )

    return f"""{SCRIBE_PERSONA.get_system_instructions()}

## Language: {ctx.deps.language}

{standards}

{ctx.deps.architecture_guardrails}

## Critical Constraints
- Do NOT modify any functional logic, algorithms, or control flow.
- ONLY add or fix: shebang line, path header comment, module docstring,
  function/class docstrings, type annotations, and variable naming.
- If a file already has correct headers and docstrings, return it unchanged.
{tools_section}
{ctx.deps.skills_content}
"""


@scribe_agent.tool  # Scope: agent-local only
async def scribe_read_file(
    ctx: RunContext[ScribeDependencies],
    file_path: str,
) -> str:
    """
    Return the content of a file for style review.

    Args:
        ctx: The run context with ScribeDependencies.
        file_path: The file path to retrieve.

    Returns:
        File content string or an error message if not found.
    """
    return ctx.deps.file_contents.get(file_path, f"ERROR: {file_path} not in provided context.")


@scribe_agent.tool  # Scope: agent-local only
async def scribe_apply_standards(
    ctx: RunContext[ScribeDependencies],
    file_path: str,
    original_content: str,
    styled_content: str,
    changes_made: list[str],
) -> str:
    """
    Record a style-corrected file patch in the run state.

    Args:
        ctx: The run context with ScribeDependencies.
        file_path: Path of the file being styled.
        original_content: Content before styling.
        styled_content: Content after applying standards.
        changes_made: List of changes that were made.

    Returns:
        Confirmation message with patch index.
    """
    patch = StyledFilePatch(
        file_path=file_path,
        original_content=original_content,
        styled_content=styled_content,
        changes_made=changes_made,
    )
    ctx.deps._scribe_patches.append(patch)
    logger.debug("Scribe styled %s (%d changes)", file_path, len(changes_made))
    return f"Standards applied to `{file_path}` — {len(changes_made)} change(s)."
