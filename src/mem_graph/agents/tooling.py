#!/usr/bin/env python3
# src/mem_graph/agents/tooling.py
"""Shared helpers for agent-local Pydantic AI tools."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import ToolDefinition

_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_]\w*$")


def hide_tool_in_preloaded_mode(
    ctx: RunContext[Any],
    tool_def: ToolDefinition,
) -> ToolDefinition | None:
    """Hide agent-local tools when a run is operating on injected file context."""
    mode = getattr(ctx.deps, "mode", "")
    extra_file_context = getattr(ctx.deps, "extra_file_context", "")
    if mode == "preloaded" or bool(extra_file_context):
        return None
    return tool_def


def require_max_items(name: str, values: Sequence[Any], *, limit: int) -> None:
    """Ask the model to retry with a smaller batch when a tool input is oversized."""
    if len(values) > limit:
        raise ModelRetry(
            f"`{name}` accepts at most {limit} item(s) per call. Retry with a smaller batch."
        )


def require_identifier(name: str, value: str) -> None:
    """Validate dynamic graph identifiers before interpolating them into queries."""
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ModelRetry(
            f"`{name}` must use letters, digits, and underscores only, and cannot start with a digit."
        )


def require_choice(name: str, value: str, *, allowed: Sequence[str]) -> None:
    """Validate small enumerated tool arguments with a retryable model error."""
    if value not in allowed:
        allowed_values = ", ".join(allowed)
        raise ModelRetry(f"`{name}` must be one of: {allowed_values}.")
