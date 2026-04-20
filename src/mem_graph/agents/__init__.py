"""mem_graph.agents package.

Pydantic AI agent definitions for routing, audit, mapping, decisions,
fixing, documentation, validation, and chat retrieval.

All 12 agents are stateless global instances. Mutable context is always
injected via typed @dataclass deps (RunContext). Import individual agents
from here for tool surfaces and orchestration.

Modules are imported with deferred model validation (defer_model_check=True)
to support fast package-level imports without requiring live model credentials.
"""

from __future__ import annotations

from .audit import audit_agent, rule_injector_agent
from .base import AGENT_BASE_CONFIG, AGENT_GROUPS, AgentConfig
from .builder import agent_builder_discovery_agent
from .document import decision_agent, scribe_agent, task_agent, triage_agent
from .fix import fixer_agent
from .map import chat_agent, map_agent, run_diagram_agent
from .orchestrator_agent import orchestrator_agent
from .router_agent import router_agent
from .validate import sentry_agent, validation_agent

__all__ = [
    # Base configuration
    "AgentConfig",
    "AGENT_BASE_CONFIG",
    "AGENT_GROUPS",
    # Orchestration group
    "orchestrator_agent",
    "router_agent",
    # Audit group
    "audit_agent",
    "rule_injector_agent",
    # Document group
    "decision_agent",
    "task_agent",
    "scribe_agent",
    "triage_agent",
    # Fix group
    "fixer_agent",
    # Map group
    "map_agent",
    "chat_agent",
    "run_diagram_agent",
    # Validate group
    "sentry_agent",
    "validation_agent",
    # Builder group
    "agent_builder_discovery_agent",
]
