#!/usr/bin/env python3
# src/mem_graph/models/work.py
"""
Task and Decision pydantic models.

Mirrors the Task and Decision node schemas from agent_memory_schema.cypher.
Provides typed I/O for work-management tools and task decomposition agents.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


################
#   ENUMS
################


class TaskStatus(str, Enum):
    """
    Lifecycle status for a Task node.

    Phases map to the TDD red/green/refactor/audit cycle used by
    the Test Architect agent and task decomposition.
    """

    PLANNING = "planning"
    RED = "red"
    GREEN = "green"
    REFACTOR = "refactor"
    AUDIT = "audit"
    DONE = "done"
    BLOCKED = "blocked"


class TaskPriority(str, Enum):
    """
    Priority classification for a Task node.

    Higher priorities surface tasks first in the sync_context workflow.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DecisionStatus(str, Enum):
    """
    Lifecycle status for a Decision node.

    SUPERSEDED decisions are replaced by a newer Decision via the
    SUPERSEDES relationship in the graph schema.
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"


################
#   MODELS
################


class TaskModel(BaseModel):
    """
    A unit of actionable work within a project.

    Maps directly to the Task node in the Kuzu graph schema.
    Tasks track TDD phases through their status field and can block
    or spawn other tasks via TASK_BLOCKS / TASK_SPAWNS relationships.
    """

    id: str = Field(description="UUIDv7 node identifier.")
    project_id: str = Field(description="Parent Project node ID.")
    title: str = Field(description="Short imperative title, e.g. 'Add rate limiter'.")
    description: str | None = Field(
        default=None,
        description="Full description including acceptance criteria.",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PLANNING,
        description="Current phase in the TDD lifecycle.",
    )
    priority: TaskPriority = Field(
        default=TaskPriority.MEDIUM,
        description="Task priority for scheduling.",
    )
    phase: str | None = Field(
        default=None,
        description="Optional sprint or iteration phase label.",
    )


class DecisionModel(BaseModel):
    """
    An architectural or technical decision with documented rationale.

    Maps directly to the Decision node in the Kuzu graph schema.
    Decisions are checked for drift by the decision_agent and linked
    to tasks via TASK_DECISION relationships.
    """

    id: str = Field(description="UUIDv7 node identifier.")
    project_id: str = Field(description="Parent Project node ID.")
    title: str = Field(description="Short decision title.")
    context: str = Field(description="What problem or situation prompted this decision.")
    rationale: str = Field(description="Why this option was chosen over alternatives.")
    alternatives: list[str] = Field(
        default_factory=list,
        description="Other options that were considered and rejected.",
    )
    status: DecisionStatus = Field(
        default=DecisionStatus.ACTIVE,
        description="Whether this decision is still in effect.",
    )
