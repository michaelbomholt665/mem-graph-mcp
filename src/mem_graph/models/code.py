#!/usr/bin/env python3
# src/mem_graph/models/code.py
"""
CodeSymbol and Tag pydantic models.

Mirrors the CodeSymbol and Tag node schemas from agent_memory_schema.cypher.
Used for traceability between code locations and graph work items
(Violations, Decisions, Tasks).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


################
#   ENUMS
################


class SymbolKind(str, Enum):
    """
    Kind of code symbol stored in the graph.

    Drives icon display and traceability link labelling in reports.
    """

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    CONSTANT = "constant"
    VARIABLE = "variable"
    MODULE = "module"
    TYPE = "type"


################
#   MODELS
################


class CodeSymbolModel(BaseModel):
    """
    A reference to a specific code symbol for traceability.

    Maps directly to the CodeSymbol node in the Kuzu graph schema.
    Linked to Tasks, Violations, and Decisions via SYMBOL_* relationships
    so graph queries can answer "what code owns this decision?".
    """

    id: str = Field(description="UUIDv7 node identifier.")
    name: str = Field(description="Symbol name as it appears in source, e.g. 'ParseRequest'.")
    kind: SymbolKind = Field(description="What type of symbol this is.")
    file_path: str = Field(description="Repo-relative path to the file containing this symbol.")
    line_start: int = Field(description="First line of the symbol definition (1-indexed).")
    line_end: int = Field(description="Last line of the symbol definition (1-indexed).")
    language: str = Field(
        default="python",
        description="Source language: go, python, typescript, etc.",
    )


class TagModel(BaseModel):
    """
    A reusable label node for cross-cutting classification.

    Maps directly to the Tag node in the Kuzu graph schema.
    Tags are attached via TAGGED relationships to any graph node
    to enable quick filtering without schema changes.
    """

    id: str = Field(description="UUIDv7 node identifier.")
    name: str = Field(description="Normalised tag name, e.g. 'auth', 'performance', 'security'.")
