#!/usr/bin/env python3
# src/mem_graph/models/memory.py
"""
Memory and Note pydantic models.

Mirrors the Memory and Note node schemas from agent_memory_schema.cypher.
Provides typed I/O for the notes and memory tools in the MCP surface.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

################
#   ENUMS
################


class MemoryKind(str, Enum):
    """
    Classification of a persisted Memory node.

    Drives recall filtering — agents can request only memories of
    specific kinds to reduce context noise when recalling.
    """

    FACT = "fact"
    PREFERENCE = "preference"
    PATTERN = "pattern"
    VIOLATION = "violation"
    ARCHITECTURE = "architecture"


class MemoryScope(str, Enum):
    """
    Scope boundary for a Memory node.

    GLOBAL memories apply across all projects; PROJECT and BACKEND
    memories are filtered to their respective graph subtree.
    """

    GLOBAL = "global"
    PROJECT = "project"
    BACKEND = "backend"


################
#   MODELS
################


class MemoryModel(BaseModel):
    """
    A distilled persistent fact stored in the graph.

    Maps directly to the Memory node in the Kuzu graph schema.
    Memories are retrieved via hybrid vector + recency search and are
    the primary mechanism for cross-session context continuity.
    """

    id: str = Field(description="UUIDv7 node identifier.")
    kind: MemoryKind = Field(description="Classification of the stored fact.")
    scope: MemoryScope = Field(
        default=MemoryScope.PROJECT,
        description="Which boundary this memory applies to.",
    )
    content: str = Field(description="The distilled fact or observation.")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Agent's confidence in this memory (0.0–1.0).",
    )
    project_id: str | None = Field(
        default=None,
        description="Project ID when scope=project or scope=backend.",
    )
    backend_id: str | None = Field(
        default=None,
        description="Backend identifier when scope=backend.",
    )


class NoteModel(BaseModel):
    """
    A free-form observation or finding attached to a project.

    Maps directly to the Note node in the Kuzu graph schema.
    Notes are less structured than Memories and are used for ad-hoc
    observations, session summaries, and autopilot run records.
    """

    id: str = Field(description="UUIDv7 node identifier.")
    project_id: str = Field(description="Parent Project node ID.")
    content: str = Field(description="Free-form text content of the note.")
    kind: str = Field(
        default="observation",
        description="Informal kind tag, e.g. 'observation', 'lesson', 'summary'.",
    )
