#!/usr/bin/env python3
# src/mem_graph/services/violation_writer.py
"""
Audit-to-graph violation writer.

Translates AuditReport findings into Violation nodes in the mem-graph
Ladybug graph. Uses SHA-256 fingerprints for stable deduplication so
that the same logical violation is never created twice. Marks recurrences
rather than duplicate nodes when a seen fingerprint is re-encountered.
"""

from __future__ import annotations

################
#   IMPORTS
################
import logging

from ..db import db_get_connection
from ..ids import id_generate_v7
from ..models.audit import AuditFinding, AuditReport
from .fingerprint import fingerprint_attach_to_findings, fingerprint_compute_hash
from .graph_writer_service import GraphWriterService

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
    seen_fingerprints: set[str] | None = None,
) -> ViolationWriteResult:
    """
    Persist all findings from an AuditReport to the graph.

    Fingerprints each finding via FingerprintService before any graph
    interaction. New fingerprints create Violation nodes; repeated
    fingerprints promote the existing node to 'recurrence'. An optional
    seen_fingerprints set allows the caller to pre-seed the filter to
    suppress findings already handled in the same orchestration run.

    Args:
        report: The AuditReport containing findings to persist.
        project_id: The Project node ID to link Violations to.
        seen_fingerprints: Optional pre-seeded dedup filter for this run.

    Returns:
        ViolationWriteResult summarising new/recurrence/skipped counts.
    """
    conn = db_get_connection()
    result = ViolationWriteResult()
    run_seen: set[str] = set(seen_fingerprints or ())

    # Attach fingerprints to all findings in-place.
    all_findings = report.all_findings
    fingerprint_attach_to_findings(all_findings)

    for finding in all_findings:
        fp = finding.fingerprint or fingerprint_compute_hash(finding)

        # Discard within-run duplicates immediately.
        if fp in run_seen:
            result.skipped += 1
            logger.debug("Skipping duplicate fingerprint %s", fp)
            continue
        run_seen.add(fp)

        existing_id = _violation_find_by_fingerprint(conn, fp, project_id)

        if existing_id:
            _violation_mark_recurrence(conn, existing_id)
            result.recurrences += 1
            result.recurrence_fingerprints.add(fp)
            logger.debug("🔄 Recurrence: violation %s (fp=%s)", existing_id, fp)
        else:
            violation_id = _violation_create_new(conn, finding, project_id, fp)
            result.created += 1
            result.new_fingerprints.add(fp)
            logger.debug("🆕 New violation %s (fp=%s)", violation_id, fp)

    result.total = len(all_findings)
    return result


################
#   GRAPH OPS
################


def _violation_find_by_fingerprint(
    conn, fingerprint: str, project_id: str
) -> str | None:
    """
    Query for an existing violation matching the given fingerprint.

    Looks up open and recurrence violations scoped to project_id.
    Falls back to an empty result (returns None) if the schema does not
    yet have a fingerprint column — the caller will treat the finding as
    new and create a fresh violation node that includes the fingerprint.

    Args:
        conn: Active Ladybug graph connection.
        fingerprint: The 16-char hex fingerprint to search for.
        project_id: The owning project's ID.

    Returns:
        The matching violation ID, or None if not found.
    """
    try:
        result = conn.execute(
            """
            MATCH (p:Project {id: $project_id})-[:HAS_VIOLATION]->(v:Violation)
            WHERE v.fingerprint = $fingerprint
              AND v.status IN ['open', 'recurrence']
            RETURN v.id
            LIMIT 1
            """,
            {"project_id": project_id, "fingerprint": fingerprint},
        )
        rows = result.get_all()
        return rows[0][0] if rows else None
    except AttributeError:
        # fingerprint column not present in this schema version — treat as new
        logger.debug("Fingerprint column missing from schema; treating finding as new.")
        return None


def _violation_create_new(
    conn,
    finding: AuditFinding,
    project_id: str,
    fingerprint: str,
) -> str:
    """
    Create a new Violation node and link it to the project.

    Stores the fingerprint on the node so future runs can detect
    recurrences via a fast fingerprint lookup instead of a composite
    key scan.

    Args:
        conn: Active Ladybug graph connection.
        finding: The AuditFinding to persist.
        project_id: The owning project's ID.
        fingerprint: Pre-computed fingerprint for this finding.

    Returns:
        The ID of the newly created Violation node.
    """
    from datetime import datetime, timezone

    violation_id = id_generate_v7()
    writer = GraphWriterService(conn)

    writer.write_node(
        label="Violation",
        properties={
            "id": violation_id,
            "audit_id": violation_id[:8].upper(),
            "rule": finding.rule_id,
            "severity": finding.severity.value,
            "file_path": finding.file_path,
            "line_start": finding.line_start,
            "line_end": finding.line_end,
            "description": f"{finding.description}\n\nFix: {finding.suggested_fix}",
            "fingerprint": fingerprint,
            "status": "open",
            "detected_at": datetime.now(timezone.utc),
        },
        parent_id=project_id,
        parent_label="Project",
        relationship_name="HAS_VIOLATION"
    )

    return violation_id


def _violation_mark_recurrence(conn, violation_id: str) -> None:
    """
    Promote an existing violation to recurrence status.

    Updates the status and records the recurrence timestamp so the
    violation lifecycle can track escalation over time.

    Args:
        conn: Active Ladybug graph connection.
        violation_id: The ID of the existing Violation node to update.
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

    Tracks how many findings were created as new violations, marked as
    recurrences, or discarded as within-run duplicates. The fingerprint
    sets allow callers (e.g. report_writer) to bucket findings accordingly.
    """

    def __init__(self) -> None:
        """Initialise all counters and fingerprint sets to empty."""
        self.total: int = 0
        self.created: int = 0
        self.recurrences: int = 0
        self.skipped: int = 0
        self.new_fingerprints: set[str] = set()
        self.recurrence_fingerprints: set[str] = set()

    def __repr__(self) -> str:
        """Return a compact string summary of write results."""
        return (
            f"ViolationWriteResult(total={self.total}, "
            f"created={self.created}, recurrences={self.recurrences}, "
            f"skipped={self.skipped})"
        )
