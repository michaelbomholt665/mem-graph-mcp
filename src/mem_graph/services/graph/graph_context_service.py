#!/usr/bin/env python3
# src/mem_graph/services/graph/graph_context_service.py
"""
GraphContextService — High-level read-only graph operations.

Extracts complex Cypher queries from agents and tools into a central,
testable service layer. Supports grounding for the orchestrator graph
and state exploration for the CLI.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ...db import db_get_connection
from ...models.work import DecisionModel, ViolationModel

logger = logging.getLogger(__name__)


class GraphContextService:
    """
    Service for querying high-level context from the knowledge graph.

    Encapsulates business-level queries (e.g. "what are the open violations?")
    away from raw Cypher, returning typed Pydantic models.
    """

    def __init__(self, conn: Any = None) -> None:
        """
        Initialise with an optional connection.

        Args:
            conn: Active Ladybug connection. If None, uses db_get_connection().
        """
        self.conn = conn or db_get_connection()

    async def query_violations(
        self,
        project_id: str,
        status: list[str] | None = None,
    ) -> list[ViolationModel]:
        """
        Get violations for a project, optionally filtered by status.

        Args:
            project_id: The project ID to filter by.
            status: List of status strings to include. Defaults to ['open', 'recurrence'].

        Returns:
            List of ViolationModel instances.
        """
        if not project_id:
            return []

        if status is None:
            status = ["open", "recurrence"]

        try:
            qr = await asyncio.to_thread(
                self.conn.execute,
                """
                MATCH (p:Project {id: $pid})-[:HAS_VIOLATION]->(v:Violation)
                WHERE v.status IN $status
                RETURN v.id, v.audit_id, v.rule, v.severity, v.file_path, 
                       v.line_start, v.line_end, v.description, v.fingerprint, 
                       v.status, v.detected_at, v.last_seen_at, v.resolved_at, p.id
                LIMIT 50
                """,
                {"pid": project_id, "status": status},
            )
            rows = qr.get_all() if hasattr(qr, "get_all") else qr
            return [
                ViolationModel(
                    id=r[0],
                    audit_id=r[1],
                    rule=r[2],
                    severity=r[3],
                    file_path=r[4],
                    line_start=r[5],
                    line_end=r[6],
                    description=r[7],
                    fingerprint=r[8],
                    status=r[9],
                    detected_at=str(r[10]) if r[10] else None,
                    last_seen_at=str(r[11]) if r[11] else None,
                    resolved_at=str(r[12]) if r[12] else None,
                    project_id=r[13],
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Could not query violations: %s", exc)
            return []

    async def query_decisions(
        self,
        project_id: str,
        limit: int = 20,
    ) -> list[DecisionModel]:
        """
        Get recent active decisions for a project.

        Args:
            project_id: The project ID to filter by.
            limit: Maximum number of decisions to return.

        Returns:
            List of DecisionModel instances.
        """
        if not project_id:
            return []

        try:
            qr = await asyncio.to_thread(
                self.conn.execute,
                """
                MATCH (p:Project {id: $pid})-[:HAS_DECISION]->(d:Decision)
                WHERE d.status = 'active'
                RETURN d.id, d.title, d.rationale, d.alternatives, d.status, p.id
                ORDER BY d.created_at DESC
                LIMIT $limit
                """,
                {"pid": project_id, "limit": limit},
            )
            rows = qr.get_all() if hasattr(qr, "get_all") else qr
            return [
                DecisionModel(
                    id=r[0],
                    title=r[1],
                    rationale=r[2],
                    alternatives=r[3].split("\n") if r[3] else [],
                    status=r[4],
                    project_id=r[5],
                    context="",  # Context property might be missing in schema, check Decision node
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Could not query decisions: %s", exc)
            return []

    async def query_map(self, project_id: str) -> str:
        """
        Fetch the most recent codebase map summary for a project.

        Args:
            project_id: The project ID to retrieve the map for.

        Returns:
            The content of the latest 'map' Note, or empty string.
        """
        if not project_id:
            return ""

        try:
            qr = await asyncio.to_thread(
                self.conn.execute,
                """
                MATCH (p:Project {id: $pid})-[:HAS_NOTE]->(n:Note)
                WHERE n.kind = 'map'
                RETURN n.content
                ORDER BY n.created_at DESC
                LIMIT 1
                """,
                {"pid": project_id},
            )
            rows = qr.get_all() if hasattr(qr, "get_all") else qr
            return str(rows[0][0]) if rows else ""
        except Exception as exc:
            logger.warning("Could not query map: %s", exc)
            return ""

    async def query_schema_counts(self) -> dict[str, int]:
        """
        Get counts of nodes in the database by type.

        Returns:
            Dict mapping label names to node counts.
        """
        counts = {}
        labels = [
            "Project",
            "Backend",
            "Task",
            "Decision",
            "Note",
            "Violation",
            "Conversation",
            "Message",
            "Memory",
            "CodeSymbol",
            "CodeFile",
            "JinaIssue",
        ]

        try:
            for label in labels:
                qr = await asyncio.to_thread(
                    self.conn.execute,
                    f"MATCH (n:{label}) RETURN count(n)",
                )
                rows = qr.get_all() if hasattr(qr, "get_all") else qr
                counts[label] = int(rows[0][0]) if rows else 0
            return counts
        except Exception as exc:
            logger.warning("Could not query schema counts: %s", exc)
            return {}

    async def query_indexes(self) -> list[dict[str, Any]]:
        """
        Get status and coverage of database indexes.

        Returns:
            List of index metadata dictionaries.
        """
        try:
            qr = await asyncio.to_thread(
                self.conn.execute,
                "CALL SHOW_INDEXES() RETURN *",
            )
            rows = qr.get_all() if hasattr(qr, "get_all") else qr
            return [
                {
                    "table": r[0],
                    "name": r[1],
                    "column": r[2],
                    "type": r[3],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Could not query indexes: %s", exc)
            return []

    async def query_project_health(self, project_id: str) -> dict[str, Any]:
        """
        Aggregate project health: violations, decisions, and map status.

        Args:
            project_id: The project ID to assess.

        Returns:
            Dict containing counts and lists of key project items.
        """
        violations = await self.query_violations(project_id)
        decisions = await self.query_decisions(project_id)
        codebase_map = await self.query_map(project_id)

        return {
            "violation_count": len(violations),
            "decision_count": len(decisions),
            "has_map": bool(codebase_map),
            "violations": violations,
            "decisions": decisions,
        }
