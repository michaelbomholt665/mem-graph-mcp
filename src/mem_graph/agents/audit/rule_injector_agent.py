#!/usr/bin/env python3
# src/mem_graph/agents/audit/rule_injector_agent.py
"""
Rule Injector Agent — dynamic AuditRule set curator.

The Librarian. Assembles the most relevant AuditRule set for a given
codebase, language, and audit scope. Bridges local default rules with
external Enforcer API rule sets for domain-specific policy injection.
"""

from __future__ import annotations

################
#   IMPORTS
################

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from ...config import DEFER_AGENT_MODEL_CHECK, ModelTier, config_get_model_for_tier
from ...models.audit import AuditRule, FindingCategory, Severity
from ...resources.personas import RULE_INJECTOR_PERSONA

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

_INJECTOR_MODEL = config_get_model_for_tier(ModelTier.TURBO)

################
#   MODELS
################


class RuleSetResult(BaseModel):
    """
    Output of the Rule Injector Agent.

    Contains the assembled set of rules ready to be passed to the
    AuditDependencies for an audit run.
    """

    rules: list[AuditRule] = Field(
        description="Selected and assembled audit rules for this scope.",
    )
    source: str = Field(
        default="local",
        description="Rule source: 'local', 'external', or 'merged'.",
    )
    rule_count: int = Field(description="Total number of rules assembled.")
    summary: str = Field(description="One-line description of the rule set scope.")


################
#   DEPS
################


@dataclass
class RuleInjectorDependencies:
    """
    Injectable dependencies for the Rule Injector Agent.

    Attributes:
        language: Target language for rule selection (python, go, typescript).
        file_extensions: File extensions in scope (e.g. ['.py', '.go']).
        scope_tags: Domain tags for rule filtering (e.g. ['auth', 'db', 'api']).
        external_api_url: Optional Enforcer API endpoint for external rules.
        extra_context: Additional context for rule relevance decisions.
    """

    language: str
    file_extensions: list[str] = field(default_factory=list)
    scope_tags: list[str] = field(default_factory=list)
    external_api_url: str | None = None
    extra_context: str = ""


################
#   AGENT
################

rule_injector_agent: Agent[RuleInjectorDependencies, RuleSetResult] = Agent(
    _INJECTOR_MODEL,
    deps_type=RuleInjectorDependencies,
    output_type=RuleSetResult,
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


@rule_injector_agent.system_prompt
async def rule_injector_build_system_prompt(
    ctx: RunContext[RuleInjectorDependencies],
) -> str:
    """
    Build the Rule Injector system prompt.

    Injects the Librarian persona and selection criteria so the agent
    assembles a tight, relevant rule set rather than a noisy catch-all.

    Args:
        ctx: The run context with RuleInjectorDependencies.

    Returns:
        Complete system prompt string.
    """
    return f"""{RULE_INJECTOR_PERSONA.get_system_instructions()}

## Your Task
Select and assemble the most relevant AuditRules for an audit of:
- Language: {ctx.deps.language}
- File extensions: {', '.join(ctx.deps.file_extensions) or 'any'}
- Scope tags: {', '.join(ctx.deps.scope_tags) or 'none'}

## Selection Criteria
1. Always include security rules (CWE-*, injection, secrets).
2. Include language-specific error handling rules.
3. Include rules that match any provided scope_tags.
4. Prefer specific rules over broad ones.
5. Exclude rules that cannot fire for the given language.

## Tools
- Call `rule_injector_list_default_rules` to see available local rules.
- Call `rule_injector_fetch_external_rules` if an external API is configured.
- Call `rule_injector_build_rule_set` to finalise your selection.

{ctx.deps.extra_context}
"""


@rule_injector_agent.tool
async def rule_injector_list_default_rules(
    ctx: RunContext[RuleInjectorDependencies],
) -> list[dict]:
    """
    Return the default local AuditRule set as serialisable dicts.

    Provides the agent with the full local rule catalogue so it can
    select the most relevant subset.

    Args:
        ctx: The run context with RuleInjectorDependencies.

    Returns:
        List of rule dicts with rule_id, category, severity, description.
    """
    default_rules = _rule_injector_get_default_rules(ctx.deps.language)
    return [r.model_dump() for r in default_rules]


@rule_injector_agent.tool
async def rule_injector_fetch_external_rules(
    ctx: RunContext[RuleInjectorDependencies],
    endpoint: str,
) -> str:
    """
    Attempt to fetch rules from an external Enforcer API endpoint.

    Returns a JSON string of rules on success, or an error message.
    The agent uses this to merge external policy with local defaults.

    Args:
        ctx: The run context with RuleInjectorDependencies.
        endpoint: The API endpoint URL to fetch rules from.

    Returns:
        JSON rule array string or error description.
    """
    if not ctx.deps.external_api_url:
        return "No external API configured — using local rules only."

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            return response.text
    except Exception as exc:
        logger.warning("Failed to fetch external rules from %s: %s", endpoint, exc)
        return f"External API unavailable: {exc}. Falling back to local rules."


################
#   HELPERS
################


def _rule_injector_get_default_rules(language: str) -> list[AuditRule]:
    """
    Return the default AuditRule set filtered to the given language.

    These rules mirror the defaults in audit_agent.py but are exposed
    here so the Librarian can inspect and selectively include them.

    Args:
        language: Target language for filtering (python, go, typescript).

    Returns:
        List of relevant default AuditRule objects.
    """
    cross_language_rules = [
        AuditRule(
            rule_id="CWE-252",
            category=FindingCategory.BUG,
            description="Unchecked return value — result of a function call is silently discarded.",
            severity=Severity.MAJOR,
        ),
        AuditRule(
            rule_id="CWE-400",
            category=FindingCategory.SECURITY,
            description="Uncontrolled resource consumption — no timeout or size limit on external calls.",
            severity=Severity.MAJOR,
        ),
        AuditRule(
            rule_id="security:hardcoded-secret",
            category=FindingCategory.SECURITY,
            description="Hardcoded credential detected — API key, password, or token in source.",
            severity=Severity.BLOCKER,
        ),
        AuditRule(
            rule_id="security:sql-injection",
            category=FindingCategory.SECURITY,
            description="SQL query constructed via string concatenation — susceptible to injection.",
            severity=Severity.CRITICAL,
        ),
        AuditRule(
            rule_id="stub:missing-implementation",
            category=FindingCategory.MISSING_IMPLEMENTATION,
            description="Stub or TODO function body — not safe to ship.",
            severity=Severity.BLOCKER,
        ),
    ]

    go_rules = [
        AuditRule(
            rule_id="go:ignored-error",
            category=FindingCategory.BUG,
            description="Error return value explicitly discarded with _ assignment.",
            severity=Severity.MAJOR,
        ),
        AuditRule(
            rule_id="go:context-propagation",
            category=FindingCategory.BUG,
            description="Context.Context not threaded through to downstream calls.",
            severity=Severity.MINOR,
        ),
        AuditRule(
            rule_id="go:goroutine-leak",
            category=FindingCategory.LEAK,
            description="Goroutine launched without a mechanism to stop or join it.",
            severity=Severity.CRITICAL,
        ),
    ]

    python_rules = [
        AuditRule(
            rule_id="py:bare-except",
            category=FindingCategory.BUG,
            description="Bare except: clause swallows all exceptions including KeyboardInterrupt.",
            severity=Severity.MAJOR,
        ),
        AuditRule(
            rule_id="py:unsafe-deserialization",
            category=FindingCategory.SECURITY,
            description="Pickle or eval used on untrusted data — arbitrary code execution risk.",
            severity=Severity.CRITICAL,
        ),
    ]

    ts_rules = [
        AuditRule(
            rule_id="ts:any-type",
            category=FindingCategory.BUG,
            description="Explicit 'any' type annotation bypasses TypeScript type safety.",
            severity=Severity.MINOR,
        ),
        AuditRule(
            rule_id="ts:floating-promise",
            category=FindingCategory.BUG,
            description="Promise returned by async function is not awaited or caught.",
            severity=Severity.MAJOR,
        ),
    ]

    lang = language.lower()
    if lang == "go":
        return cross_language_rules + go_rules
    if lang == "python":
        return cross_language_rules + python_rules
    if lang in ("typescript", "ts"):
        return cross_language_rules + ts_rules
    return cross_language_rules
