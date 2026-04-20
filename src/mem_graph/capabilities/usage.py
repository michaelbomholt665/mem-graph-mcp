#!/usr/bin/env python3
# src/mem_graph/capabilities/usage.py
"""
UsageTrackingCapability — post-run token usage logging.

Provides a lightweight `after_run` hook that logs token consumption for every
agent run. Pass ``agent_name`` at construction to distinguish agents in logs.

The primary motivation is task 039: each delegated sub-agent run now produces
a visible usage line in structured logs, enabling downstream aggregation without
requiring changes to individual agent implementations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.run import AgentRunResult

logger = logging.getLogger(__name__)


@dataclass
class UsageTrackingCapability(AbstractCapability[Any]):
    """Log token usage after every agent run.

    Attach to any agent at construction time:

        agent = Agent(
            model,
            capabilities=[UsageTrackingCapability(agent_name="audit")],
        )

    Emits a single ``INFO`` log line per run with request count and token totals.
    This capability is observe-only: it never modifies the run result.

    Attributes:
        agent_name: Label used in log messages. Falls back to the agent's own
            ``name`` attribute when left empty.
    """

    agent_name: str = field(default="")

    async def after_run(
        self,
        ctx: RunContext[Any],
        *,
        result: AgentRunResult[Any],
    ) -> AgentRunResult[Any]:
        """Emit a usage log line and return the result unchanged."""
        usage = result.usage()
        name = (
            self.agent_name
            or getattr(ctx, "agent", None)
            and getattr(ctx.agent, "name", "unknown")
            or "unknown"
        )
        logger.info(
            "[USAGE] agent=%s requests=%d input_tokens=%d output_tokens=%d "
            "cache_read=%d cache_write=%d",
            name,
            usage.requests,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_write_tokens,
        )
        return result
