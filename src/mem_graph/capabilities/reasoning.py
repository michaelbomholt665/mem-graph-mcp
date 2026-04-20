#!/usr/bin/env python3
# src/mem_graph/capabilities/reasoning.py
"""
ReasoningStrategyCapability — cross-cutting reasoning-mode instruction injection.

Replaces the repeated `reasoning_hint` pattern found across 10+ agent instruction
builders. Any agent whose deps carry a `reasoning_mode` field benefits automatically
once this capability is registered at construction time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability

from ..resources.prompts import get_reasoning_mode_guidance


@dataclass
class ReasoningStrategyCapability(AbstractCapability[Any]):
    """Append reasoning-mode guidance to agents that carry ``deps.reasoning_mode``.

    Added once at agent construction via ``capabilities=[ReasoningStrategyCapability()]``.
    Replaces the identical per-agent ``reasoning_hint`` f-string blocks that were
    scattered across every specialist agent.

    Behavior:
    - When ``ctx.deps.reasoning_mode`` is non-empty, appends a ``## Reasoning Strategy``
      section drawn from the central prompt registry.
    - When the mode is absent or empty, returns an empty string so the system prompt
      is unchanged.
    - Uses ``getattr`` with a default so agents whose deps do not define
      ``reasoning_mode`` are silently skipped rather than raising.
    """

    def get_instructions(
        self,
    ) -> Callable[[RunContext[Any]], str | None] | None:
        """Return a per-run callable that appends reasoning guidance when active."""

        def _reasoning_instructions(ctx: RunContext[Any]) -> str | None:
            mode: str = getattr(ctx.deps, "reasoning_mode", "")
            if not mode:
                return ""
            guidance = get_reasoning_mode_guidance(mode)
            if not guidance:
                return ""
            return f"\n\n## Reasoning Strategy\n{guidance}"

        return _reasoning_instructions
