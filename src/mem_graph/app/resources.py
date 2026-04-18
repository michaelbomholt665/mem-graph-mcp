"""MCP resource templates."""

from __future__ import annotations

import json
from typing import Any, cast

from fastmcp import FastMCP

from ..db import db_get_connection


def register_resources(mcp: FastMCP) -> None:
    @mcp.resource(
        "memory://{memory_id}",
        description="Read a stored memory node by its ID.",
        mime_type="application/json",
    )
    async def resource_memory(memory_id: str) -> str:
        conn = db_get_connection()
        result = conn.execute(
            """
            MATCH (m:Memory {id: $id})
            OPTIONAL MATCH (m)<-[:PROJECT_MEMORY]-(p:Project)
            RETURN m.id, m.kind, m.scope, m.content, m.confidence,
                   m.created_at, m.updated_at, m.expires_at, p.name AS project
            """,
            {"id": memory_id},
        )
        if isinstance(result, list):
            result = result[0]
        rows = cast(list[list[Any]], result.get_all())
        if not rows:
            return json.dumps({"error": f"Memory {memory_id!r} not found"})
        row = rows[0]
        return json.dumps(
            {
                "id": row[0],
                "kind": row[1],
                "scope": row[2],
                "content": row[3],
                "confidence": row[4],
                "created_at": str(row[5]),
                "updated_at": str(row[6]),
                "expires_at": str(row[7]) if row[7] else None,
                "project": row[8],
            }
        )

    @mcp.resource(
        "memory://list",
        description="List the 50 most recently created active memories.",
        mime_type="application/json",
    )
    async def resource_memory_list() -> str:
        conn = db_get_connection()
        result = conn.execute(
            """
            MATCH (m:Memory)
            WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
            RETURN m.id, m.kind, m.scope, m.content, m.confidence, m.created_at
            ORDER BY m.created_at DESC
            LIMIT 50
            """
        )
        if isinstance(result, list):
            result = result[0]
        memories = [
            {
                "id": row[0],
                "kind": row[1],
                "scope": row[2],
                "content": row[3],
                "confidence": row[4],
                "created_at": str(row[5]),
            }
            for row in cast(list[list[Any]], result.get_all())
        ]
        return json.dumps({"memories": memories, "count": len(memories)})

    @mcp.resource(
        "work://tasks/{task_id}",
        description="Read a work task node by its ID.",
        mime_type="application/json",
    )
    async def resource_task(task_id: str) -> str:
        conn = db_get_connection()
        result = conn.execute(
            """
            MATCH (t:Task {id: $id})
            RETURN t.id, t.title, t.description, t.status, t.priority,
                   t.phase, t.created_at, t.updated_at, t.completed_at
            """,
            {"id": task_id},
        )
        if isinstance(result, list):
            result = result[0]
        rows = cast(list[list[Any]], result.get_all())
        if not rows:
            return json.dumps({"error": f"Task {task_id!r} not found"})
        row = rows[0]
        return json.dumps(
            {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "status": row[3],
                "priority": row[4],
                "phase": row[5],
                "created_at": str(row[6]),
                "updated_at": str(row[7]),
                "completed_at": str(row[8]) if row[8] else None,
            }
        )

    @mcp.resource(
        "work://projects/{project_id}",
        description="Read a project node, its tasks, and open violations by project ID.",
        mime_type="application/json",
    )
    async def resource_project(project_id: str) -> str:
        conn = db_get_connection()
        result = conn.execute(
            """
            MATCH (p:Project {id: $id})
            RETURN p.id, p.name, p.description, p.status, p.repo_path, p.created_at
            """,
            {"id": project_id},
        )
        if isinstance(result, list):
            result = result[0]
        rows = cast(list[list[Any]], result.get_all())
        if not rows:
            return json.dumps({"error": f"Project {project_id!r} not found"})
        row = rows[0]
        task_count = _count(
            "MATCH (p:Project {id: $id})-[:HAS_TASK]->(t) RETURN count(t)",
            {"id": project_id},
        )
        viol_count = _count(
            "MATCH (p:Project {id: $id})-[:HAS_VIOLATION]->(v) WHERE v.status = 'open' RETURN count(v)",
            {"id": project_id},
        )
        return json.dumps(
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "status": row[3],
                "repo_path": row[4],
                "created_at": str(row[5]),
                "task_count": task_count,
                "open_violation_count": viol_count,
            }
        )

    @mcp.resource(
        "audit://violations/{violation_id}",
        description="Read a code violation node by its ID.",
        mime_type="application/json",
    )
    async def resource_violation(violation_id: str) -> str:
        conn = db_get_connection()
        result = conn.execute(
            """
            MATCH (v:Violation {id: $id})
            OPTIONAL MATCH (p:Project)-[:HAS_VIOLATION]->(v)
            RETURN v.id, v.audit_id, v.rule, v.severity, v.status,
                   v.file_path, v.description, v.detected_at, v.resolved_at, p.id AS project_id
            """,
            {"id": violation_id},
        )
        if isinstance(result, list):
            result = result[0]
        rows = cast(list[list[Any]], result.get_all())
        if not rows:
            return json.dumps({"error": f"Violation {violation_id!r} not found"})
        row = rows[0]
        return json.dumps(
            {
                "id": row[0],
                "audit_id": row[1],
                "rule": row[2],
                "severity": row[3],
                "status": row[4],
                "file_path": row[5],
                "description": row[6],
                "detected_at": str(row[7]),
                "resolved_at": str(row[8]) if row[8] else None,
                "project_id": row[9],
            }
        )


def _count(query: str, params: dict[str, Any]) -> int:
    result = db_get_connection().execute(query, params)
    if isinstance(result, list):
        result = result[0]
    rows = cast(list[list[Any]], result.get_all())
    return int(rows[0][0]) if rows else 0

