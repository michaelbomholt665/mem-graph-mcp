"""Audit agent factory helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic_ai import Agent

from ...config import ModelTier, config_get_model_for_tier
from ...models.audit import AuditReport, AuditRule
from ...resources.personas import AUDITOR_PERSONA, Persona
from .audit_agent import AuditDependencies, audit_agent
from .rules import audit_rules_get

AuditToolMode = Literal["standalone", "preloaded"]


@dataclass(frozen=True)
class AuditAgentBundle:
    """Factory output describing an audit agent and its fixed configuration."""

    agent: Agent[AuditDependencies, AuditReport]
    deps: AuditDependencies
    persona: Persona
    model: str
    rules: list[AuditRule]
    tool_mode: AuditToolMode


def build_audit_agent_bundle(
    *,
    package_path: str,
    rule_set: str = "default",
    tool_mode: AuditToolMode = "standalone",
    file_extension: str = ".py",
    skills_content: str = "",
    extra_file_context: str = "",
    model_tier: str | ModelTier = ModelTier.STANDARD,
) -> AuditAgentBundle:
    """
    Build a consistently wired audit-agent bundle.

    The returned bundle selects persona, rule set, model tier, output type,
    and tool surface mode in one place. The single audit_agent instance is
    used for all modes; mode branching is driven by deps.mode at runtime.
    """
    rules = audit_rules_get(rule_set)
    deps = AuditDependencies(
        package_path=package_path,
        rules=rules,
        file_extension=file_extension,
        skills_content=skills_content,
        extra_file_context=extra_file_context,
        mode=tool_mode,
    )
    return AuditAgentBundle(
        agent=audit_agent,
        deps=deps,
        persona=AUDITOR_PERSONA,
        model=config_get_model_for_tier(model_tier),
        rules=rules,
        tool_mode=tool_mode,
    )
