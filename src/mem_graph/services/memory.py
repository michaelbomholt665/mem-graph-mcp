"""Instrumented memory service used by the MCP tool surface."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from ..embeddings import embeddings_query
from ..ids import id_generate_v7
from ..observability import logfire_info, traced_span


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _content_fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


class MemoryService:
    """Encapsulate memory persistence with safe observability metadata."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def store(
        self,
        *,
        content: str,
        kind: str,
        scope: str,
        project_id: str | None,
    ) -> str:
        memory_id = id_generate_v7()
        with traced_span(
            "memory.store",
            attributes={
                "memory.kind": kind,
                "memory.scope": scope,
                "memory.project_linked": bool(project_id),
                "memory.content_length": len(content),
            },
        ):
            vec = await embeddings_query(content)
            timestamp = _now()
            self._conn.execute(
                """
                CREATE (m:Memory {
                    id: $id,
                    kind: $kind,
                    scope: $scope,
                    content: $content,
                    confidence: 1.0,
                    embedding: $embedding,
                    created_at: $ts,
                    updated_at: $ts
                })
                """,
                {
                    "id": memory_id,
                    "kind": kind,
                    "scope": scope,
                    "content": content,
                    "embedding": vec,
                    "ts": timestamp,
                },
            )

            if project_id:
                self._conn.execute(
                    """
                    MATCH (p:Project {id: $project_id}), (m:Memory {id: $mem_id})
                    CREATE (p)-[:PROJECT_MEMORY]->(m)
                    """,
                    {"project_id": project_id, "mem_id": memory_id},
                )

        logfire_info(
            "Memory stored",
            memory_id=memory_id,
            kind=kind,
            scope=scope,
            project_linked=bool(project_id),
            content_length=len(content),
            content_fingerprint=_content_fingerprint(content),
        )
        return memory_id

    def expire(self, memory_id: str) -> dict[str, str]:
        with traced_span(
            "memory.expire",
            attributes={"memory.id": memory_id},
        ):
            timestamp = _now()
            expired_at = timestamp - timedelta(seconds=1)
            self._conn.execute(
                """
                MATCH (m:Memory {id: $id})
                SET m.expires_at = $expires_at, m.updated_at = $ts
                """,
                {"id": memory_id, "expires_at": expired_at, "ts": timestamp},
            )

        logfire_info("Memory expired", memory_id=memory_id)
        return {"memory_id": memory_id, "status": "expired"}

    def list_active(
        self,
        *,
        scope: str | None,
        project_id: str | None,
    ) -> list[dict[str, Any]]:
        with traced_span(
            "memory.list",
            attributes={
                "memory.scope_filter": scope or "all",
                "memory.project_filter": bool(project_id),
            },
        ):
            if project_id:
                result = self._conn.execute(
                    """
                    MATCH (p:Project {id: $project_id})-[:PROJECT_MEMORY]->(m:Memory)
                    WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
                    RETURN m.id, m.kind, m.scope, m.content, m.confidence, m.created_at
                    ORDER BY m.created_at DESC
                    """,
                    {"project_id": project_id},
                )
            else:
                result = self._conn.execute(
                    """
                    MATCH (m:Memory)
                    WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
                    RETURN m.id, m.kind, m.scope, m.content, m.confidence, m.created_at
                    ORDER BY m.created_at DESC
                    """
                )

            memories = [
                {
                    "id": row[0],
                    "kind": row[1],
                    "scope": row[2],
                    "content": row[3],
                    "confidence": row[4],
                    "created_at": str(row[5]),
                }
                for row in cast(list[list[Any]], result)
                if scope is None or row[2] == scope
            ]

        logfire_info(
            "Memories listed",
            scope=scope or "all",
            project_scoped=bool(project_id),
            result_count=len(memories),
        )
        return memories
