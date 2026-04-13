#!/usr/bin/env python3
# src/mem_graph/models/project.py
"""
Project and Backend pydantic models.

Mirrors the Project and Backend node schemas from agent_memory_schema.cypher.
Used for tool I/O and typed agent output across the mem-graph surface.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


################
#   ENUMS
################


class ProjectStatus(str, Enum):
    """
    Lifecycle status for a Project node.

    Drives display filtering and auto-archival logic in the graph.
    """

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class BackendLanguage(str, Enum):
    """
    Primary language for a Backend node.

    Determines which agent pair (Go, Python, TypeScript) handles analysis.
    """

    GO = "go"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    OTHER = "other"


################
#   MODELS
################


class ProjectModel(BaseModel):
    """
    A top-level project isolation boundary.

    Maps directly to the Project node in the Kuzu graph schema.
    All work items (Tasks, Decisions, Violations) are linked through a Project.
    """

    id: str = Field(description="UUIDv7 node identifier.")
    name: str = Field(description="Short human-readable project name.")
    description: str | None = Field(
        default=None,
        description="Longer narrative description of the project's purpose.",
    )
    language: BackendLanguage = Field(
        default=BackendLanguage.PYTHON,
        description="Primary programming language for this project.",
    )
    status: ProjectStatus = Field(
        default=ProjectStatus.ACTIVE,
        description="Current lifecycle status of the project.",
    )


class BackendModel(BaseModel):
    """
    A language/service boundary within a project.

    Backends represent distinct codebases or services within a project
    (e.g., go-core, python-analytics). Violations and Maps are scoped
    to a Backend, not just a Project.
    """

    id: str = Field(description="UUIDv7 node identifier.")
    project_id: str = Field(description="Parent Project node ID.")
    name: str = Field(description="Short backend name, e.g. 'go-core' or 'py-analytics'.")
    language: BackendLanguage = Field(
        description="Primary language for this backend service.",
    )
    description: str | None = Field(
        default=None,
        description="What this backend is responsible for.",
    )
