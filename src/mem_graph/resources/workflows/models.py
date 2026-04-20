#!/usr/bin/env python3
# src/mem_graph/resources/workflows/models.py
"""Typed Pydantic models for Python-defined workflow resources."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ProfileSize(str, Enum):
    """Size-based orchestration profile selector."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class ReasoningMode(str, Enum):
    """Reasoning policy mode for the main AI before final action choice."""

    REACT_CHALLENGE = "react_challenge"
    REACT_2 = "react_2"
    BOUNDED_TOT = "bounded_tot"
    COT = "cot"


class StagePolicy(BaseModel):
    """Constraints applied to a single workflow stage."""

    name: str = Field(description="Workflow stage name this policy covers.")
    allowed_agents: list[str] = Field(
        default_factory=list,
        description="Agent names permitted in this stage.",
    )
    parallel: bool = Field(
        default=False,
        description="Whether sub-agents in this stage may run in parallel.",
    )
    retry_allowed: bool = Field(
        default=False,
        description="Whether this stage may be retried on failure.",
    )
    tool_budget: int = Field(
        default=10,
        ge=1,
        description="Maximum tool calls permitted per stage instance.",
    )


class WorkflowSandboxPolicy(BaseModel):
    """Sandbox defaults associated with a workflow profile or resource."""

    enabled: bool = Field(
        default=False,
        description="Whether this workflow should request a session sandbox.",
    )
    image: str = Field(
        default="python:3.14-slim",
        description="Container image used for sandbox sessions.",
    )
    network: Literal["none", "bridge"] = Field(
        default="none",
        description="Container network mode; none is the secure default.",
    )
    memory: str = Field(default="1g", description="Container memory limit.")
    cpus: str = Field(default="2", description="Container CPU limit.")
    exec_timeout_seconds: int = Field(default=30, ge=1)
    session_ttl_seconds: int = Field(default=3600, ge=1)
    merge_back: bool = Field(
        default=False,
        description="Whether successful workflow validation may merge workspace changes back.",
    )
    retain_artifacts: bool = Field(
        default=False,
        description="Retain workspace/snapshot after cleanup for debugging.",
    )


class WorkflowProfile(BaseModel):
    """Size-based orchestration profile defining runtime constraints."""

    size: ProfileSize = Field(description="Profile size: small, medium, or large.")
    description: str = Field(description="Human-readable profile intent.")
    max_stages: int = Field(description="Maximum number of stages in a run.", ge=1)
    fan_out_limit: int = Field(
        description="Maximum parallel sub-agents allowed at once.",
        ge=1,
    )
    retry_cycles: int = Field(
        description="Maximum validation/retry cycles allowed.",
        ge=0,
    )
    checkpoint_frequency: int = Field(
        default=0,
        description="Persist state every N stages. 0 = no intermediate checkpoints.",
        ge=0,
    )
    stage_policies: list[StagePolicy] = Field(
        default_factory=list,
        description="Per-stage policy overrides.",
    )
    sandbox_policy: WorkflowSandboxPolicy = Field(
        default_factory=WorkflowSandboxPolicy,
        description="Default sandbox policy for workflows using this profile.",
    )


class ReasoningPolicy(BaseModel):
    """Deterministic reasoning policy enforced before final action choice."""

    mode: ReasoningMode = Field(description="Reasoning mode.")
    description: str = Field(description="Human-readable policy description.")
    required_steps: list[str] = Field(
        description="Ordered reasoning steps that must be completed."
    )
    tree_width: int = Field(
        default=0,
        description="ToT branch width. 0 = not applicable.",
        ge=0,
    )
    tree_depth: int = Field(
        default=0,
        description="ToT exploration depth. 0 = not applicable.",
        ge=0,
    )
    pruning_criteria: list[str] = Field(
        default_factory=list,
        description="Criteria used to prune ToT branches early.",
    )
    budget_cap: int = Field(
        default=0,
        description="Maximum reasoning tokens/steps for bounded ToT. 0 = not applicable.",
        ge=0,
    )


class WorkflowStageDefinition(BaseModel):
    """Single stage definition within a workflow resource."""

    name: str = Field(description="Unique stage identifier within the workflow.")
    description: str = Field(description="What this stage does.")
    agent: str | None = Field(
        default=None,
        description="Agent responsible for this stage.",
    )
    allowed_tools: list[str] = Field(
        default_factory=list,
        description="Tool names permitted in this stage.",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Names of stages that must complete before this one starts.",
    )
    parallel_with: list[str] = Field(
        default_factory=list,
        description="Names of stages that may run concurrently with this one.",
    )
    artifacts: list[str] = Field(
        default_factory=list,
        description="Named artifact outputs produced by this stage.",
    )


class WorkflowResource(BaseModel):
    """A typed Python-defined workflow resource."""

    key: str = Field(description="Unique workflow identifier.")
    display_name: str = Field(description="Human-readable workflow name.")
    description: str = Field(description="What this workflow accomplishes.")
    profile: ProfileSize = Field(description="Default profile size for this workflow.")
    task_types: list[str] = Field(
        default_factory=list,
        description="Task types this workflow handles.",
    )
    stages: list[WorkflowStageDefinition] = Field(
        default_factory=list,
        description="Ordered stage definitions.",
    )
    reasoning_mode: ReasoningMode = Field(
        default=ReasoningMode.REACT_CHALLENGE,
        description="Default reasoning policy applied before each major decision.",
    )
    risk_level: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Risk level that informs retry and checkpoint policies.",
    )
    source_module: str = Field(
        default="",
        description="Python module path where the runtime lives.",
    )
    sandbox_policy: WorkflowSandboxPolicy | None = Field(
        default=None,
        description="Optional workflow-specific sandbox policy override.",
    )
