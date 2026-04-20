"""
Base configuration for all mem_graph agents.

Provides shared settings, agent group registry, and the canonical
agent inventory. Import from here to avoid importing heavy agent
modules at configuration time.
"""

from __future__ import annotations

from dataclasses import dataclass

################
#   AGENT CONFIG
################


@dataclass
class AgentConfig:
    """Shared settings for all agents.

    These are the default values used at agent construction time.
    Individual agents may override temperature/top_p via
    config_model_settings() when their persona specifies different values.
    """

    defer_model_check: bool = True
    temperature: float = 0.5  # overridable per-agent via persona settings
    top_p: float = 0.9


AGENT_BASE_CONFIG = AgentConfig()

################
#   AGENT GROUPS
################

AGENT_GROUPS: dict[str, list[str]] = {
    "orchestration": ["orchestrator_agent", "router_agent"],
    "audit": ["audit_agent", "rule_injector_agent"],
    "document": ["decision_agent", "task_agent", "scribe_agent", "triage_agent"],
    "fix": ["fixer_agent"],
    "map": ["map_agent", "chat_agent", "diagram_agent"],
    "validate": ["sentry_agent", "validation_agent"],
    "builder": ["agent_builder_discovery_agent"],
}

"""
Agent Instantiation Pattern
===========================

Every agent is instantiated once at module load as a stateless global instance.
All mutable context flows through a typed @dataclass injected via RunContext.

Example:

    audit_agent: Agent[AuditDependencies, AuditReport] = Agent(
        AGENT_MODEL,
        name="audit",
        deps_type=AuditDependencies,
        output_type=AuditReport,
        model_settings=config_model_settings(temperature=0.2, top_p=0.9),
        defer_model_check=DEFER_AGENT_MODEL_CHECK,
    )

Agent-local tools are decorated with # Scope: agent-local only and must NOT
be registered in the MCP tool registry or tools/__init__.py.

State Accumulation Pattern
==========================

All per-run mutable state lives in the deps dataclass:

    @dataclass
    class AuditDependencies:
        package_path: str
        rules: list[AuditRule] = field(default_factory=list)
        file_results: list[FileAuditResult] = field(default_factory=list)
        # ^^^ accumulated during the run, never monkey-patched onto ctx

Mutable state must live in deps dataclass fields only, never on RunContext.
"""
