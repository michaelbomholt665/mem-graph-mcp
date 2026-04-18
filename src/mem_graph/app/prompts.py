"""MCP prompt registrations."""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from ..resources.prompts import PROMPT_REGISTRY, get_sub_agent_instructions


def register_prompts(mcp: FastMCP) -> None:
    @mcp.prompt(
        name="sync_context",
        description="Project Sync: Re-orient and align your knowledge.",
    )
    def prompt_sync_context() -> str:
        return PROMPT_REGISTRY["sync_context"]

    @mcp.prompt(name="plan_feature", description="Feature Architect: Decompose and design.")
    def prompt_plan_feature() -> str:
        return PROMPT_REGISTRY["plan_feature"]

    @mcp.prompt(name="run_audit", description="Quality Audit: Bugs and drift analysis.")
    def prompt_run_audit() -> str:
        return PROMPT_REGISTRY["run_audit"]

    @mcp.prompt(name="close_session", description="Session Wrap: Summarize and persist.")
    def prompt_close_session() -> str:
        return PROMPT_REGISTRY["close_session"]

    @mcp.prompt(
        name="sub_agent_spinup",
        description="Initialize a specialized sub-agent persona.",
    )
    def prompt_sub_agent_spinup(
        persona: Annotated[
            str, Field(description="Persona key: auditor | architect | triage | mapper")
        ],
        task: Annotated[
            str, Field(description="The specific task the sub-agent should perform")
        ],
    ) -> str:
        return get_sub_agent_instructions(persona, task)

