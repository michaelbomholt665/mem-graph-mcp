#!/usr/bin/env python3
# src/mem_graph/services/report_writer.py
"""
Audit report renderer.

Converts a structured AuditReport into a human-readable markdown document.
Organised by severity first, then by file, so the most critical issues
are always at the top regardless of discovery order.
"""

from __future__ import annotations

################
#   IMPORTS
################

from pathlib import Path

from ..models.audit import AuditFinding, AuditReport, AuditStats, Severity

################
#   BUCKETING LABELS
################

_NEW_LABEL = "🆕 New"
_RECUR_LABEL = "🔄 Recurring"

################
#   CONSTANTS
################

_SEVERITY_EMOJI: dict[str, str] = {
    Severity.BLOCKER.value: "🚨",
    Severity.CRITICAL.value: "🔴",
    Severity.MAJOR.value: "🟠",
    Severity.MINOR.value: "🟡",
    Severity.INFO.value: "🔵",
}

_SEVERITY_ORDER = [
    Severity.BLOCKER,
    Severity.CRITICAL,
    Severity.MAJOR,
    Severity.MINOR,
    Severity.INFO,
]


################
#   PUBLIC API
################


def render_markdown(
    report: AuditReport,
    recurrence_fingerprints: set[str] | None = None,
) -> str:
    """
    Render a complete AuditReport as a markdown string.

    Produces a document with a header, stats table, executive summary,
    findings grouped by severity (with New vs. Recurring bucketing when
    recurrence_fingerprints is provided), and a skipped files appendix.
    Ready to write to disk or display in a terminal.

    Args:
        report: The AuditReport to render.
        recurrence_fingerprints: Optional set of fingerprints that were
            matched as recurrences during the write_violations call.
            When provided, findings are sub-bucketed into 🆕 New and
            🔄 Recurring within each severity group.

    Returns:
        A complete markdown string.
    """
    sections: list[str] = [
        _render_header(report),
        _render_stats_table(report.stats),
        _render_summary(report),
        _render_findings_by_severity(report.all_findings, recurrence_fingerprints),
        _render_skipped_files(report),
    ]

    return "\n\n".join(s for s in sections if s.strip())


def write_report(
    report: AuditReport,
    output_path: str,
    recurrence_fingerprints: set[str] | None = None,
) -> str:
    """
    Render and write the audit report to disk.

    Creates parent directories if they do not exist.

    Args:
        report: The AuditReport to render.
        output_path: Destination file path.
        recurrence_fingerprints: Optional set of recurrence fingerprints
            from ViolationWriteResult.recurrence_fingerprints for bucketing.

    Returns:
        The resolved output path on success.
    """
    content = render_markdown(report, recurrence_fingerprints)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path.resolve())


################
#   SECTIONS
################


def _render_header(report: AuditReport) -> str:
    """Render the document title and audit metadata."""
    blocker_warning = (
        "\n> ⛔ **This audit contains BLOCKER findings. Do not ship.**"
        if report.has_blockers
        else ""
    )
    partial_warning = (
        "\n> ⚠️ **Partial failure: some files may not have been fully analysed.**"
        if report.partial_failure
        else ""
    )

    return (
        f"# Audit Report\n\n"
        f"**Package**: `{report.package_path}`  \n"
        f"**Rules applied**: {len(report.rules_applied)}  \n"
        f"**Total findings**: {report.stats.total_findings}"
        f"{blocker_warning}"
        f"{partial_warning}"
    )


def _render_stats_table(stats: AuditStats) -> str:
    """Render a markdown table summarising finding counts by severity."""
    rows: list[str] = []

    for severity in _SEVERITY_ORDER:
        count = stats.by_severity.get(severity.value, 0)
        if count == 0:
            continue
        emoji = _SEVERITY_EMOJI[severity.value]
        rows.append(f"| {emoji} {severity.value.capitalize()} | {count} |")

    if not rows:
        return "## Stats\n\nNo findings."

    table = "| Severity | Count |\n|---|---|\n" + "\n".join(rows)
    skipped_line = (
        f"\n\n*{stats.total_files_skipped} file(s) skipped — see appendix.*"
        if stats.total_files_skipped > 0
        else ""
    )

    return f"## Stats\n\n{table}{skipped_line}"


def _render_summary(report: AuditReport) -> str:
    """Render the agent's narrative summary."""
    return f"## Summary\n\n{report.summary}"


def _render_findings_by_severity(
    findings: list[AuditFinding],
    recurrence_fingerprints: set[str] | None = None,
) -> str:
    """
    Render all findings grouped by severity in descending order.

    Within each severity group, findings are further grouped by file
    to make file-level patterns visible. When recurrence_fingerprints
    is provided, each file group is sub-bucketed into 🆕 New and
    🔄 Recurring findings.

    Args:
        findings: All audit findings to render.
        recurrence_fingerprints: Optional set of fingerprints that were
            recurrences during the last violation write.

    Returns:
        Markdown string for the Findings section.
    """
    if not findings:
        return "## Findings\n\nNo findings."

    blocks: list[str] = ["## Findings"]

    for severity in _SEVERITY_ORDER:
        group = [f for f in findings if f.severity == severity]
        if not group:
            continue

        emoji = _SEVERITY_EMOJI[severity.value]
        blocks.append(f"### {emoji} {severity.value.capitalize()}")

        by_file = _group_by_file(group)
        for file_path, file_findings in by_file.items():
            blocks.append(
                _render_file_findings(file_path, file_findings, recurrence_fingerprints)
            )

    return "\n\n".join(blocks)


def _render_file_findings(
    file_path: str,
    findings: list[AuditFinding],
    recurrence_fingerprints: set[str] | None = None,
) -> str:
    """
    Render all findings for a single file as a markdown subsection.

    When recurrence_fingerprints is provided, splits findings into
    🆕 New and 🔄 Recurring sub-buckets beneath the file header.

    Args:
        file_path: The source file path for the section header.
        findings: All findings for this file.
        recurrence_fingerprints: Optional set of recurrence fingerprints.

    Returns:
        Markdown string for this file's findings block.
    """
    lines: list[str] = [f"#### `{file_path}`"]

    if recurrence_fingerprints is not None:
        new_findings = [
            f for f in findings
            if f.fingerprint not in recurrence_fingerprints
        ]
        recurring_findings = [
            f for f in findings
            if f.fingerprint in recurrence_fingerprints
        ]

        if new_findings:
            lines.append(f"**{_NEW_LABEL}**")
            for finding in new_findings:
                lines.append(_render_single_finding(finding))

        if recurring_findings:
            lines.append(f"**{_RECUR_LABEL}**")
            for finding in recurring_findings:
                lines.append(_render_single_finding(finding))
    else:
        for finding in findings:
            lines.append(_render_single_finding(finding))

    return "\n\n".join(lines)


def _render_single_finding(finding: AuditFinding) -> str:
    """Render a single AuditFinding as a markdown block."""
    location = f"L{finding.line_start}–{finding.line_end}"
    snippet_block = (
        f"\n```\n{finding.code_snippet}\n```"
        if finding.code_snippet
        else ""
    )

    return (
        f"**[{finding.rule_id}]** {location}  \n"
        f"{finding.description}  \n"
        f"*Fix*: {finding.suggested_fix}"
        f"{snippet_block}"
    )


def _render_skipped_files(report: AuditReport) -> str:
    """Render an appendix listing files that were skipped during analysis."""
    skipped = [fr for fr in report.file_results if fr.skipped]

    if not skipped:
        return ""

    rows = "\n".join(
        f"- `{fr.file_path}` — {fr.skip_reason or 'unknown reason'}"
        for fr in skipped
    )

    return f"## Appendix: Skipped Files\n\n{rows}"


################
#   HELPERS
################


def _group_by_file(findings: list[AuditFinding]) -> dict[str, list[AuditFinding]]:
    """
    Group findings by file path preserving discovery order.

    Uses dict insertion order (Python 3.7+) to maintain stability
    across runs when findings are sorted by severity first.
    """
    grouped: dict[str, list[AuditFinding]] = {}

    for finding in findings:
        grouped.setdefault(finding.file_path, []).append(finding)

    return grouped