"""Dashboard telemetry and database helpers."""

from __future__ import annotations

import logging
from typing import Any, cast

from ..db import db_get_connection

logger = logging.getLogger(__name__)


def query_rows(query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    conn = db_get_connection()
    result = conn.execute(query, params or {})
    if isinstance(result, list):
        result = result[0]
    return cast(list[list[Any]], result.get_all())


def safe_count(query: str, params: dict[str, Any] | None = None) -> int:
    try:
        rows = query_rows(query, params)
    except Exception:  # noqa: BLE001
        return 0
    return int(rows[0][0]) if rows else 0


def dashboard_graph_telemetry() -> dict[str, Any]:
    node_labels = [
        "Agent",
        "Project",
        "Backend",
        "Task",
        "Decision",
        "Note",
        "Violation",
        "Memory",
        "Message",
        "CodeFile",
        "CodeSymbol",
        "JinaIssue",
        "EvalRun",
    ]
    relationship_names = [
        "HAS_BACKEND",
        "HAS_TASK",
        "HAS_DECISION",
        "HAS_NOTE",
        "HAS_VIOLATION",
        "HAS_FILE",
        "HAS_JINA_ISSUE",
        "HAS_EVAL_RUN",
        "PROJECT_MEMORY",
        "BACKEND_TASK",
        "BACKEND_DECISION",
        "BACKEND_SYMBOL",
        "BACKEND_VIOLATION",
        "TASK_BLOCKS",
        "TASK_SPAWNS",
        "TASK_DECISION",
        "TASK_VIOLATION",
        "TASK_NOTE",
        "DECISION_NOTE",
        "SUPERSEDES",
        "VIOLATION_RECURS",
        "SYMBOL_TASK",
        "SYMBOL_VIOLATION",
        "SYMBOL_DECISION",
        "AUTHORED_BY",
        "IMPLEMENTS",
        "MENTIONS",
    ]
    return {
        "node_count": safe_count("MATCH (n) RETURN count(n)"),
        "edge_count": safe_count("MATCH ()-[r]->() RETURN count(r)"),
        "node_counts": _node_counts(node_labels),
        "edge_counts": _relationship_counts(relationship_names),
        "task_status": _grouped_counts(
            "MATCH (t:Task) RETURN t.status, count(t) ORDER BY t.status"
        ),
        "violation_severity": _grouped_counts(
            "MATCH (v:Violation) RETURN v.severity, count(v) ORDER BY v.severity"
        ),
    }


def _node_counts(labels: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = safe_count(f"MATCH (n:{label}) RETURN count(n)")
    return counts


def _relationship_counts(names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rel_name in names:
        counts[rel_name] = safe_count(f"MATCH ()-[r:{rel_name}]->() RETURN count(r)")
    return counts


def _grouped_counts(query: str) -> dict[str, int]:
    try:
        return {str(row[0] or "unknown"): int(row[1]) for row in query_rows(query)}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed dashboard grouped count: %s", exc)
        return {}

