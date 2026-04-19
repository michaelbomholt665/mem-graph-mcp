#!/usr/bin/env python3
# src/mem_graph/models/conversation.py
"""
models/conversation.py — Pydantic I/O models for conversation capture tools.

These types are returned (not bare ``dict``) so FastMCP generates accurate
JSON schema entries in the tool catalog, and AI callers receive rich type
hints without parsing raw dictionaries.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    """A single message turn submitted to ``memory_capture_session``."""

    role: Literal["user", "assistant", "system", "tool"] = Field(
        description="Message role: user | assistant | system | tool"
    )
    content: str = Field(description="Message text content")
    tool_name: str | None = Field(
        default=None,
        description="Tool name — populate only when role='tool'",
    )


class SessionCaptureResult(BaseModel):
    """Immediate response from ``memory_capture_session``."""

    session_id: str = Field(description="Stable ID for the captured session")
    turn_count: int = Field(description="Number of messages persisted")
    summary_pending: bool = Field(
        description=(
            "True when summarisation has been queued but not yet completed. "
            "The summary will be written to the Conversation node asynchronously."
        )
    )


class MemoryItem(BaseModel):
    """A single recalled memory or conversation excerpt."""

    id: str
    kind: str
    scope: str
    content: str
    confidence: float
    project: str | None
    distance: float


class MemoryRecallResult(BaseModel):
    """Response from ``memory_recall``."""

    memories: list[MemoryItem] = Field(
        description="Ranked memory items fit to the requested token budget"
    )
    total_tokens: int = Field(
        description="Approximate token count of all returned memory content"
    )
    truncated: bool = Field(
        description="True if results were cut to respect budget_tokens"
    )
    query: str = Field(description="The original query string")


class AnnotateResult(BaseModel):
    """Response from ``memory_annotate``."""

    memory_id: str = Field(description="ID of the newly created Memory node")
    linked_to_session: str = Field(
        description="Conversation ID this annotation is linked to"
    )
