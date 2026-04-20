#!/usr/bin/env python3
# src/mem_graph/agents/document/triage_agent.py
"""
Violation triage agent.

Second-pass review over violations — either raw findings from external
tools (policycheck output, manual notes) or existing violations already
in the graph. Deduplicates, re-assesses severity, promotes recurrences,
and classifies findings into actionable buckets. Input source is
controlled by the caller via TriageDependencies.
"""

from __future__ import annotations

################
#   IMPORTS
################
import logging
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from ...capabilities import ReasoningStrategyCapability
from ...config import AGENT_MODEL, DEFER_AGENT_MODEL_CHECK, config_model_settings
from ...resources.personas import TRIAGE_PERSONA

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)


################
#   MODELS
################


class TriageDecision(str, Enum):
    """
    Triage outcome for a single violation candidate.

    Drives what the violation writer does with the finding downstream.
    """

    NEW = "new"
    RECURRENCE = "recurrence"
    DUPLICATE = "duplicate"
    WONTFIX = "wontfix"
    ESCALATE = "escalate"


class RawFinding(BaseModel):
    """
    An unvalidated finding from an external tool or manual note.

    Input unit for the triage agent when processing tool output.
    Rule, file, and description are the minimum viable fields.
    Line numbers and severity are best-effort from external tools.
    """

    rule_id: str = Field(description="Rule or policy ID that fired.")
    file_path: str = Field(description="File containing the finding.")
    line_start: int = Field(default=0, description="Line number, 0 if unknown.")
    line_end: int = Field(default=0, description="End line, 0 if unknown.")
    severity: str = Field(
        default="minor", description="Reported severity from source tool."
    )
    description: str = Field(
        description="Raw finding description from the source tool."
    )
    source: str = Field(
        default="unknown",
        description="Origin: 'policycheck', 'manual', 'audit_agent', etc.",
    )


class TriagedViolation(BaseModel):
    """
    A triage decision for a single finding.

    Produced by the agent after assessing the finding against existing
    violations and domain context. Consumed by the violation writer.
    """

    raw: RawFinding = Field(description="The original finding being triaged.")
    decision: TriageDecision = Field(description="Triage outcome.")
    assessed_severity: str = Field(
        description="Agent-assessed severity, may differ from raw.severity."
    )
    rationale: str = Field(
        description="Why this decision was made — used in report and graph note."
    )
    existing_violation_id: str | None = Field(
        default=None,
        description="Graph violation ID if this is a recurrence or duplicate.",
    )
    suggested_owner: str | None = Field(
        default=None,
        description="File or package that should own the fix.",
    )


class TriageReport(BaseModel):
    """
    Complete triage output for a batch of raw findings.

    Contains all triage decisions and summary counts. Consumed by
    the violation writer and report renderer downstream.
    """

    project_id: str = Field(description="Project this triage run belongs to.")
    decisions: list[TriagedViolation] = Field(default_factory=list)
    summary: str = Field(description="Narrative summary of triage decisions.")
    total_input: int = Field(description="Number of raw findings processed.")
    new_count: int = Field(default=0)
    recurrence_count: int = Field(default=0)
    duplicate_count: int = Field(default=0)
    escalated_count: int = Field(default=0)
    wontfix_count: int = Field(default=0)
    partial_failure: bool = Field(default=False)


################
#   DEPS
################


@dataclass
class TriageDependencies:
    """
    Injectable dependencies for the triage agent.

    raw_findings: external tool output to triage from scratch.
    existing_violations: serialised graph violations for re-assessment.
    Either or both may be populated — the agent handles both paths.
    project_id is required for graph context queries.
    _triage_state: accumulated TriagedViolation objects;
        never monkey-patched onto RunContext.
    """

    project_id: str
    raw_findings: list[RawFinding] = field(default_factory=list)
    existing_violations: list[dict] = field(default_factory=list)
    skills_content: str = ""
    _triage_state: list["TriagedViolation"] = field(default_factory=list)
    reasoning_mode: str = ""


################
#   AGENT
################

triage_agent: Agent[TriageDependencies, TriageReport] = Agent(
    AGENT_MODEL,
    name="triage",
    deps_type=TriageDependencies,
    output_type=TriageReport,
    model_settings=config_model_settings(
        temperature=TRIAGE_PERSONA.params.temperature,
        top_p=TRIAGE_PERSONA.params.top_p,
    ),
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
    capabilities=[ReasoningStrategyCapability()],
)


################
#   PROMPTS
################


@triage_agent.instructions
async def build_instructions(ctx: RunContext[TriageDependencies]) -> str:
    """
    Build the system prompt from deps and the Triage persona at runtime.
    """
    persona_instr = TRIAGE_PERSONA.get_system_instructions()
    skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."
    raw_block = _format_raw_findings(ctx.deps.raw_findings)
    existing_block = _format_existing_violations(ctx.deps.existing_violations)

    return f"""{persona_instr}

## Domain Knowledge
{skills_block}

## Raw Findings to Triage
{raw_block}

## Existing Open Violations in Graph
{existing_block}

## Triage Rules
1. Call `process_batch` iteratively. Submit your `decisions_from_previous_batch` and ask to process the next batch of finding indices (up to 5 finding indices at a time).
2. Assess whether findings are genuinely new, a recurrence, or a duplicate.
3. Re-assess severity based on full context — escalate if the impact is worse than reported.
4. Continue calling `process_batch` until all findings are triaged.
5. Provide an empty index list on your final `process_batch` call.

## Decision Criteria
- NEW: No matching open violation. Finding is confirmed and actionable.
- RECURRENCE: Matching open violation exists. Promote it — do not create a duplicate.
- DUPLICATE: Identical finding already triaged in this batch. Discard.
- WONTFIX: Finding is real but accepted risk or out of scope. Document rationale.
- ESCALATE: Finding is more severe than reported — override severity and flag for immediate attention.

After all findings are triaged, call `finalize_triage` with a summary.

Be precise. Do not mark something WONTFIX without a specific rationale.
Do not mark something DUPLICATE unless it is genuinely the same finding in the same file and lines.
"""


def _format_raw_findings(findings: list[RawFinding]) -> str:
    """Render raw findings as a numbered list for the system prompt."""
    if not findings:
        return "No raw findings provided — operating in graph re-assessment mode."

    lines = []
    for i, f in enumerate(findings, 1):
        lines.append(
            f"{i}. [{f.rule_id}] {f.file_path}:{f.line_start} ({f.severity}) "
            f"via {f.source}\n   {f.description}"
        )
    return "\n".join(lines)


def _format_existing_violations(violations: list[dict]) -> str:
    """Render existing graph violations as a reference list."""
    if not violations:
        return (
            "No existing violations provided — treat all findings as potentially new."
        )

    lines = []
    for v in violations:
        lines.append(
            f"- [{v.get('id', '?')}] {v.get('rule', '?')} "
            f"{v.get('file_path', '?')}:{v.get('line_start', '?')} "
            f"status={v.get('status', '?')}"
        )
    return "\n".join(lines)


################
#   TOOLS
################


@triage_agent.tool  # Scope: agent-local only
async def process_batch(
    ctx: RunContext[TriageDependencies],
    finding_indices: list[int],
    decisions_from_previous_batch: list[TriagedViolation],
) -> str:
    """
    Submit decisions from the previous batch and retrieve the next batch of findings
    and their matching existing violations.

    Pass indices (0 to len(raw_findings)-1) to select up to 5 raw findings at a time.
    Returns the finding details and any existing violations that match by rule and file.
    Pass an empty list for findings_indices on the final call.
    """
    _get_state(ctx).extend(decisions_from_previous_batch)

    results = []
    for idx in finding_indices[:5]:
        if idx < 0 or idx >= len(ctx.deps.raw_findings):
            results.append(f"### Index {idx}\nERROR: Index out of bounds.")
            continue

        finding = ctx.deps.raw_findings[idx]
        matching = [
            v
            for v in ctx.deps.existing_violations
            if v.get("rule") == finding.rule_id
            and v.get("file_path") == finding.file_path
        ]

        match_str = (
            "No existing matches."
            if not matching
            else (
                "Found matching existing violation(s):\n"
                + "\n".join(
                    [
                        f"- [{v.get('id', '?')}] status={v.get('status', '?')}"
                        for v in matching
                    ]
                )
            )
        )

        results.append(
            f"### Index {idx}: [{finding.rule_id}] {finding.file_path}:{finding.line_start}\n"
            f"Description: {finding.description}\n"
            f"{match_str}"
        )

    if not results:
        return "No findings requested. Decisions stored."

    return "\n\n".join(results)


@triage_agent.tool  # Scope: agent-local only
async def finalize_triage(
    ctx: RunContext[TriageDependencies],
    summary: str,
    partial_failure: bool = False,
) -> TriageReport:
    """
    Aggregate all triage decisions into the final TriageReport.

    Called once after all findings have been assessed. Computes
    summary counts from recorded decisions.
    """
    decisions = _get_state(ctx)
    counts = _compute_counts(decisions)

    return TriageReport(
        project_id=ctx.deps.project_id,
        decisions=decisions,
        summary=summary,
        total_input=len(ctx.deps.raw_findings) or len(ctx.deps.existing_violations),
        partial_failure=partial_failure,
        **counts,
    )


################
#   HELPERS
################


def _get_state(ctx: RunContext[TriageDependencies]) -> list[TriagedViolation]:
    """Retrieve the per-run decision accumulator from deps (never monkey-patched)."""
    return ctx.deps._triage_state


def _compute_counts(decisions: list[TriagedViolation]) -> dict:
    """Compute summary counts from a list of triage decisions."""
    return {
        "new_count": sum(1 for d in decisions if d.decision == TriageDecision.NEW),
        "recurrence_count": sum(
            1 for d in decisions if d.decision == TriageDecision.RECURRENCE
        ),
        "duplicate_count": sum(
            1 for d in decisions if d.decision == TriageDecision.DUPLICATE
        ),
        "escalated_count": sum(
            1 for d in decisions if d.decision == TriageDecision.ESCALATE
        ),
        "wontfix_count": sum(
            1 for d in decisions if d.decision == TriageDecision.WONTFIX
        ),
    }
