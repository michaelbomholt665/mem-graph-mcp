#!/usr/bin/env python3
# src/mem_graph/capabilities/__init__.py
"""
mem_graph capabilities.

Reusable `AbstractCapability` implementations that bundle cross-cutting
concerns — reasoning strategy, usage tracking — so they can be composed
onto agents at construction time rather than duplicated per module.

Usage::

    from mem_graph.capabilities import ReasoningStrategyCapability, UsageTrackingCapability

    my_agent = Agent(
        model,
        capabilities=[
            ReasoningStrategyCapability(),
            UsageTrackingCapability(agent_name="my-agent"),
        ],
    )
"""

from .reasoning import ReasoningStrategyCapability
from .usage import UsageTrackingCapability

__all__ = [
    "ReasoningStrategyCapability",
    "UsageTrackingCapability",
]
