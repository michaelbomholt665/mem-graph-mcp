from typing import Any, List, Optional
from ..db import db_get_connection

class GraphContextService:
    def __init__(self, conn: Any = None):
        self.conn = conn or db_get_connection()

    def _rows(self, query: str, params: Optional[dict[str, Any]] = None) -> List[List[Any]]:
        result = self.conn.execute(query, params or {})
        if isinstance(result, list):
            result = result[0]
        return result.get_all()

    def query_violations(self, project_id: str) -> List[dict[str, Any]]:
        """Get open violations for a project."""
        rows = self._rows(
            """
            MATCH (p:Project {id: $project_id})-[:HAS_VIOLATION]->(v:Violation)
            WHERE v.status IN ['open', 'recurrence']
            RETURN v.id, v.rule, v.description, v.severity, v.status, v.file_path
            ORDER BY v.detected_at DESC
            """,
            {"project_id": project_id}
        )
        return [{"id": r[0], "rule": r[1], "description": r[2], "severity": r[3], "status": r[4], "file_path": r[5]} for r in rows]

    def query_decisions(self, project_id: str) -> List[dict[str, Any]]:
        """Get recent decisions for a project."""
        rows = self._rows(
            """
            MATCH (p:Project {id: $project_id})-[:HAS_DECISION]->(d:Decision)
            RETURN d.id, d.title, d.rationale, d.status, d.impact
            ORDER BY d.created_at DESC
            """,
            {"project_id": project_id}
        )
        return [{"id": r[0], "title": r[1], "rationale": r[2], "status": r[3], "impact": r[4]} for r in rows]

    def query_map(self, project_id: str) -> dict:
        """Get codebase map (files and tasks)."""
        # simplified
        return {"files": [], "tasks": []}

    def query_schema_counts(self) -> dict:
        """Get counts of nodes in DB by type."""
        # This isn't purely standard cypher but works in ladybug/neo4j
        rows = self._rows("MATCH (n) RETURN labels(n)[0], count(*)")
        return {r[0]: r[1] for r in rows if r[0]}

    def query_indexes(self) -> List[dict]:
        """Get index status."""
        # Typically requires schema APIs, mock implementation for now
        return []

