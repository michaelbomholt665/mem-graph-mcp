#!/usr/bin/env python3
# src/mem_graph/models/audit.py
"""
Audit data models.

Defines the structured output types for the audit agent — findings,
file-level results, aggregated reports, and injectable rule definitions.
These models are the contract between the agent, the report writer,
and the violation writer.
"""

from __future__ import annotations

################
#   IMPORTS
################
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

################
#   ENUMS
################


class Severity(str, Enum):
    """
    Standardised finding severity levels.

    Mirrors the Violation node severity enum in the graph schema
    so findings can be written directly without translation.
    """

    INFO = "info"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"
    BLOCKER = "blocker"


class FindingCategory(str, Enum):
    """
    Top-level category for classifying what kind of problem was found.

    Drives report grouping and downstream triage routing.
    """

    BUG = "bug"
    LEAK = "leak"
    SILENT_ERROR = "silent_error"
    SECURITY = "security"
    MISSING_IMPLEMENTATION = "missing_implementation"
    COMPLEXITY = "complexity"
    OTHER = "other"


################
#   MODELS
################


class AuditRule(BaseModel):
    """
    A single injectable audit rule.

    Rules are passed via AuditDependencies to specialise the generic
    agent for a specific domain (e.g. lakehouse invariants). Each rule
    has a stable ID, human description, severity hint, and optional
    examples to guide the LLM's pattern recognition.
    """

    rule_id: str = Field(
        description="Stable rule identifier, e.g. 'CWE-252', 'security:sql-injection', or 'lakehouse:frozen-schema'."
    )
    category: FindingCategory = Field(
        description="Top-level category this rule belongs to, such as security, bug, or complexity."
    )
    description: str = Field(
        description="What this rule checks for. Written for LLM consumption, so it should describe the failure mode precisely enough to support self-correction."
    )
    severity: Severity = Field(
        description="Default severity when this rule fires, for example blocker for hardcoded secrets or major for unchecked errors."
    )
    examples: list[str] = Field(
        default_factory=list,
        description="Short code snippets illustrating violations of this rule.",
    )


class AuditFinding(BaseModel):
    """
    A single confirmed issue found in a source file.

    Atomic unit of audit output. Carries enough information to write
    a Violation node to the graph and render a meaningful report entry.
    The fingerprint field is populated by FingerprintService before the
    finding is passed to violation_writer for stable deduplication.
    """

    rule_id: str = Field(
        description="Rule that fired, e.g. 'CWE-252', 'go:ignored-error', 'security:hardcoded-secret'."
    )
    category: FindingCategory = Field(
        description="Top-level category for grouping and triage."
    )
    severity: Severity = Field(
        description="Assessed severity of this specific instance."
    )
    file_path: str = Field(
        description="Absolute or repo-relative path to the file containing this finding."
    )
    line_start: int = Field(
        ge=1,
        description="1-indexed line where the finding begins. Use the nearest relevant statement or function boundary when exact precision is uncertain.",
    )
    line_end: int = Field(
        ge=1,
        description="1-indexed line where the finding ends. This must be greater than or equal to line_start.",
    )

    @model_validator(mode="after")
    def _check_line_range(self) -> "AuditFinding":
        if self.line_end < self.line_start:
            raise ValueError(
                f"line_end ({self.line_end}) must be >= line_start ({self.line_start})"
            )
        return self

    description: str = Field(
        description="Clear explanation of what is wrong, why it matters, and what concrete risk or failure mode it introduces."
    )
    suggested_fix: str = Field(
        description="Concrete replacement or remediation action to resolve the finding, not a vague recommendation."
    )
    code_snippet: Annotated[
        str | None,
        Field(
            description="Literal offending code lines copied from the file for inline review; do not paraphrase or summarize.",
            default=None,
        ),
    ]
    fingerprint: str | None = Field(
        default=None,
        description=(
            "SHA-256 fingerprint (16-char hex) computed from file_path + rule_id + "
            "normalised code_snippet. Populated by FingerprintService. "
            "Used by violation_writer for stable deduplication across audit runs."
        ),
    )


class FileAuditResult(BaseModel):
    """
    Audit output for a single source file.

    Intermediate model produced per-file during the agent's analysis
    loop. Aggregated into AuditReport at the end of the run.
    """

    file_path: str = Field(
        description="Path to the analysed file as presented to the audit agent and downstream report writers."
    )
    findings: list[AuditFinding] = Field(
        default_factory=list,
        description="All findings identified in this file.",
    )
    skipped: bool = Field(
        default=False,
        description="True if the file was skipped due to a read error or size limit.",
    )
    skip_reason: str | None = Field(
        default=None,
        description="Reason the file was skipped, populated only when skipped=True so downstream summaries can explain partial coverage.",
    )


class AuditStats(BaseModel):
    """
    Summary counts derived from an AuditReport.

    Provides a quick overview without iterating over all findings.
    """

    total_files_analysed: int = Field(
        description="Count of files fully analysed during the audit run."
    )
    total_files_skipped: int = Field(
        description="Count of files skipped because of read failures, size limits, or explicit exclusions."
    )
    total_findings: int = Field(
        description="Total number of findings produced across all successfully analysed files."
    )
    by_severity: dict[str, int] = Field(
        description="Finding count keyed by Severity value so reports can summarize risk distribution quickly."
    )
    by_category: dict[str, int] = Field(
        description="Finding count keyed by FindingCategory value for grouping bugs, leaks, security issues, and other classes."
    )
    blocker_count: int = Field(
        description="Number of blocker-severity findings that should stop a release or require immediate attention."
    )
    critical_count: int = Field(
        description="Number of critical-severity findings that demand urgent remediation but may not hard-block execution."
    )


class AuditReport(BaseModel):
    """
    Complete audit output for a package or directory.

    Top-level result returned by the audit agent. Contains all
    per-file results, aggregated stats, a human-readable summary,
    and a flag indicating whether any tool calls failed during the run.
    """

    package_path: str = Field(
        description="Root path or package identifier that scoped the audit run."
    )
    summary: str = Field(
        description="Human-readable narrative summary of the audit findings, including the most important risks and overall cleanliness of the target."
    )
    file_results: list[FileAuditResult] = Field(
        default_factory=list,
        description="Per-file audit results in analysis order.",
    )
    stats: AuditStats = Field(description="Aggregated finding counts.")
    rules_applied: list[str] = Field(
        description="Rule IDs that were active during this audit run, in the order they were supplied to the audit agent."
    )
    partial_failure: bool = Field(
        default=False,
        description="True when one or more tool calls failed after all retries.",
    )

    @property
    def all_findings(self) -> list[AuditFinding]:
        """
        Flatten all per-file findings into a single ordered list.

        Returns findings in file order, preserving the order findings
        were discovered within each file.
        """
        return [f for fr in self.file_results for f in fr.findings]

    @property
    def has_blockers(self) -> bool:
        """Return True if any finding has BLOCKER severity."""
        return any(f.severity == Severity.BLOCKER for f in self.all_findings)
