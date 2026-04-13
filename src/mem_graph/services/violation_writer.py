#!/usr/bin/env python3
# src/mem_graph/services/violation_writer.py
"""
Audit-to-graph violation writer.

Translates AuditReport findings into Violation nodes in the mem-graph
Ladybug graph. Deduplicates against existing open violations by rule_id
and file_path before writing, and marks recurrences rather than creating
duplicate nodes.
"""

from __future__ import annotations

################
#   IMPORTS
################

import logging

from ..db import get_conn
from ..ids import new_id
from ..models.audit import AuditFinding, AuditReport

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

################
#   PUBLIC API
################


def write_violations(
    report: AuditReport,
    project_id: str,
) -> ViolationWriteResult:
    """
    Persist all findings from an AuditReport to the graph.

    Deduplicates by (rule_id, file_path, line_start) against open
    violations. New findings create Violation nodes linked to the
    project. Matching open violations are promoted to recurrence status.

    Returns a summary of what was written vs what was deduplicated.
    """
    conn = get_conn()
    result = ViolationWriteResult()

    for finding in report.all_findings:
        existing_id = _find_existing_violation(conn, finding, project_id)

        if existing_id:
            _mark_recurrence(conn, existing_id)
            result.recurrences += 1
            logger.debug("Marked recurrence for violation %s", existing_id)
        else:
            violation_id = _create_violation(conn, finding, project_id)
            result.created += 1
            logger.debug("Created violation %s for %s", violation_id, finding.rule_id)

    result.total = len(report.all_findings)
    return result


################
#   GRAPH OPS
################


def _find_existing_violation(conn, finding: AuditFinding, project_id: str) -> str | None:
    """
    Query for an existing open violation matching this finding.

    Matches on rule_id, file_path, and line_start within the given
    project. Returns the violation ID if found, None otherwise.
    """
    result = conn.execute(
        """
        MATCH (p:Project {id: $project_id})-[:HAS_VIOLATION]->(v:Violation)
        WHERE v.rule = $rule
          AND v.file_path = $file_path
          AND v.line_start = $line_start
          AND v.status IN ['open', 'recurrence']
        RETURN v.id
        LIMIT 1
        """,
        {
            "project_id": project_id,
            "rule": finding.rule_id,
            "file_path": finding.file_path,
            "line_start": finding.line_start,
        },
    )
    rows = result.get_all()
    return rows[0][0] if rows else None


def _create_violation(conn, finding: AuditFinding, project_id: str) -> str:
    """
    Create a new Violation node and link it to the project.

    Returns the new violation ID.
    """
    from datetime import datetime, timezone

    violation_id = new_id()
    now = datetime.now(timezone.utc)

    conn.execute(
        """
        CREATE (v:Violation {
            id: $id,
            audit_id: $audit_id,
            rule: $rule,
            severity: $severity,
            file_path: $file_path,
            line_start: $line_start,
            line_end: $line_end,
            description: $description,
            status: 'open',
            detected_at: $ts
        })
        """,
        {
            "id": violation_id,
            "audit_id": violation_id[:8].upper(),
            "rule": finding.rule_id,
            "severity": finding.severity.value,
            "file_path": finding.file_path,
            "line_start": finding.line_start,
            "line_end": finding.line_end,
            "description": f"{finding.description}\n\nFix: {finding.suggested_fix}",
            "ts": now,
        },
    )

    conn.execute(
        """
        MATCH (p:Project {id: $project_id}), (v:Violation {id: $violation_id})
        CREATE (p)-[:HAS_VIOLATION]->(v)
        """,
        {"project_id": project_id, "violation_id": violation_id},
    )

    return violation_id


def _mark_recurrence(conn, violation_id: str) -> None:
    """
    Promote an existing violation to recurrence status.

    Updates the status and records the recurrence timestamp so the
    violation lifecycle can track escalation over time.
    """
    from datetime import datetime, timezone

    conn.execute(
        """
        MATCH (v:Violation {id: $id})
        SET v.status = 'recurrence',
            v.last_seen_at = $ts
        """,
        {"id": violation_id, "ts": datetime.now(timezone.utc)},
    )


################
#   RESULT
################


class ViolationWriteResult:
    """
    Summary of a violation write operation.

    Tracks how many findings were created as new violations versus
    marked as recurrences of existing ones.
    """

    def __init__(self) -> None:
        """Initialise all counters to zero."""
        self.total: int = 0
        self.created: int = 0
        self.recurrences: int = 0

    def __repr__(self) -> str:
        """Return a compact string summary of write results."""
        return (
            f"ViolationWriteResult(total={self.total}, "
            f"created={self.created}, recurrences={self.recurrences})"
        )