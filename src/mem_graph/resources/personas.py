"""Compatibility re-exports for persona resources.

Persona definitions live in :mod:`mem_graph.resources.prompts.personas`.
This module preserves the historical import path used by agents.
"""

from __future__ import annotations

from .prompts.personas import (
    AGENT_BUILDER_PERSONA,
    ARCHITECT_PERSONA,
    AUDITOR_PERSONA,
    CHAT_PERSONA,
    GUARD_PERSONA,
    MAPPER_PERSONA,
    MECHANIC_PERSONA,
    PERSONA_REGISTRY,
    ROUTER_PERSONA,
    RULE_INJECTOR_PERSONA,
    SCRIBE_PERSONA,
    SENTRY_PERSONA,
    TRIAGE_PERSONA,
    BigFiveTraits,
    LLMParams,
    Persona,
    render_ocean_trait,
)

__all__ = [
    "AGENT_BUILDER_PERSONA",
    "ARCHITECT_PERSONA",
    "AUDITOR_PERSONA",
    "CHAT_PERSONA",
    "GUARD_PERSONA",
    "MAPPER_PERSONA",
    "MECHANIC_PERSONA",
    "PERSONA_REGISTRY",
    "ROUTER_PERSONA",
    "RULE_INJECTOR_PERSONA",
    "SCRIBE_PERSONA",
    "SENTRY_PERSONA",
    "TRIAGE_PERSONA",
    "BigFiveTraits",
    "LLMParams",
    "Persona",
    "render_ocean_trait",
]
