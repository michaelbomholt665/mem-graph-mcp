#!/usr/bin/env python3
# src/mem_graph/models/work.py
"""
Task and Decision pydantic models.

Mirrors the Task and Decision node schemas from agent_memory_schema.cypher.
Provides typed I/O for work-management tools and task decomposition agents.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field

################
#   ENUMS
################


class WorkTaskStatus(str, Enum):
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


# Backwards-compatible alias.
TaskStatus = WorkTaskStatus


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
#   CONSTANTS
################

ID_DESCRIPTION = "UUIDv7 node identifier."
PROJECT_ID_DESCRIPTION = "Parent Project node ID."
WorkTaskPhase: TypeAlias = Literal["planning", "red", "green", "refactor", "audit"]
ViolationSeverity: TypeAlias = Literal[
    "info",
    "minor",
    "major",
    "critical",
    "blocker",
]
ViolationStatus: TypeAlias = Literal["open", "recurrence", "resolved", "graduated"]


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

    id: str = Field(description=ID_DESCRIPTION)
    project_id: str = Field(description=PROJECT_ID_DESCRIPTION)
    title: str = Field(
        description="Short imperative title that stays scannable in task lists, e.g. 'Add rate limiter'."
    )
    description: str | None = Field(
        default=None,
        description="Expanded task narrative including motivation, scope, and acceptance criteria.",
    )
    status: WorkTaskStatus = Field(
        default=WorkTaskStatus.PLANNING,
        description="Current lifecycle state of the task within the planning-to-delivery flow.",
    )
    priority: TaskPriority = Field(
        default=TaskPriority.MEDIUM,
        description="Task priority used for scheduling and surfacing urgent work first.",
    )
    phase: WorkTaskPhase | None = Field(
        default=None,
        description="Optional explicit TDD phase label when the task needs more precise sequencing than status alone.",
    )


class DecisionModel(BaseModel):
    """
    An architectural or technical decision with documented rationale.

    Maps directly to the Decision node in the Kuzu graph schema.
    Decisions are checked for drift by the decision_agent and linked
    to tasks via TASK_DECISION relationships.
    """

    id: str = Field(description=ID_DESCRIPTION)
    project_id: str = Field(description=PROJECT_ID_DESCRIPTION)
    title: str = Field(
        description="Short decision title that can stand alone in reports and graph views."
    )
    context: str = Field(
        description="What problem, constraint, or operational context prompted this decision."
    )
    rationale: str = Field(
        description="Why this option was chosen over alternatives, including the trade-offs it optimizes for."
    )
    alternatives: list[str] = Field(
        default_factory=list,
        description="Other options that were considered and rejected, ideally with enough detail to explain the trade-off.",
    )
    status: DecisionStatus = Field(
        default=DecisionStatus.ACTIVE,
        description="Whether this decision is active, superseded by a newer decision, or deprecated.",
    )


class ViolationModel(BaseModel):
    """
    A policy violation or audit finding persisted in the graph.

    Maps directly to the Violation node in the Kuzu graph schema.
    """

    id: str = Field(description=ID_DESCRIPTION)
    project_id: str = Field(description=PROJECT_ID_DESCRIPTION)
    audit_id: str | None = Field(
        default=None,
        description="Short human-readable identifier shown in reports or issue trackers, when available.",
    )
    rule: str = Field(
        description="Stable rule identifier that describes the violated policy or audit check."
    )
    severity: ViolationSeverity = Field(
        default="info",
        description="Severity assigned to this violation after triage or audit classification.",
    )
    file_path: str = Field(
        description="Repo-relative or absolute path to the file containing the violation."
    )
    line_start: int = Field(
        ge=1,
        description="1-indexed line where the violation begins, using the nearest relevant boundary when exact precision is unavailable.",
    )
    line_end: int = Field(
        ge=1,
        description="1-indexed line where the violation ends, which must be greater than or equal to line_start.",
    )
    description: str = Field(
        description="Concrete explanation of what is wrong, why it matters, and what behavior or policy it violates."
    )
    fingerprint: str | None = Field(
        default=None,
        description="Stable deduplication fingerprint derived from the rule, file, and normalized code snippet.",
    )
    status: ViolationStatus = Field(
        default="open",
        description="Lifecycle state for this violation as it moves from detection through remediation.",
    )
    detected_at: str | None = Field(
        default=None,
        description="Timestamp when this violation was first detected, typically encoded as ISO-8601 text.",
    )
    last_seen_at: str | None = Field(
        default=None,
        description="Timestamp when this violation was most recently observed during a later audit or validation run.",
    )
    resolved_at: str | None = Field(
        default=None,
        description="Timestamp when the violation was marked resolved, if remediation has completed.",
    )
