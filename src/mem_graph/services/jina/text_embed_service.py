"""Jina issue fetching, persistence, and semantic matching."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import httpx

from ...db import db_get_connection, db_update_embedding
from .code_embed_service import CodeEmbedService, ensure_project_link, rows
from ..embed_client import EmbedClientBase
from .jina_common import (
    DEFAULT_TIMEOUT_SECONDS,
    DONE_STATUSES,
    CodeMatch,
    JinaConfigurationError,
    JinaIssue,
    TicketMatch,
    bool_has_value,
    cosine_similarity,
    extract_snippet,
    flatten_description,
    now_utc,
    parse_timestamp,
)

EmbeddingFn = Callable[[str], Awaitable[list[float]]]


class TextEmbedService(EmbedClientBase):
    """Fetch Jina issues and coordinate issue-to-code semantic matching."""

    def __init__(
        self,
        *,
        jina_url: str,
        jina_username: str | None,
        jina_token: str | None,
        project_key: str | None,
        match_threshold: float,
        max_results: int,
        transport: httpx.AsyncBaseTransport | None,
        code_service: CodeEmbedService,
        embeddings_code: EmbeddingFn,
        embeddings_code_query: EmbeddingFn,
    ) -> None:
        super().__init__(model="jina-api")
        self.jina_url = jina_url.rstrip("/")
        self.jina_username = jina_username
        self.jina_token = jina_token
        self.project_key = project_key
        self.match_threshold = match_threshold
        self.max_results = max(1, max_results)
        self._transport = transport
        self._code_service = code_service
        self._embeddings_code = embeddings_code
        self._embeddings_code_query = embeddings_code_query

    @property
    def configured(self) -> bool:
        return bool_has_value(self.jina_url) and bool_has_value(self.jina_token)

    def default_jql(self) -> str:
        if bool_has_value(self.project_key):
            return f'project = "{self.project_key}" ORDER BY updated DESC'
        return "updated >= -30d ORDER BY updated DESC"

    async def fetch_issues(
        self,
        *,
        jql: str | None = None,
        limit: int | None = None,
    ) -> list[JinaIssue]:
        self.require_configuration()
        bounded_limit = min(max(limit or self.max_results, 1), self.max_results)
        bounded_jql = (jql or self.default_jql()).strip()
        if len(bounded_jql) > 500:
            raise ValueError("JQL must be 500 characters or fewer.")

        async def _fetch() -> dict[str, Any]:
            headers = {"Accept": "application/json"}
            client_kwargs: dict[str, Any] = {
                "base_url": self.jina_url,
                "headers": headers,
                "timeout": DEFAULT_TIMEOUT_SECONDS,
            }
            if self._transport is not None:
                client_kwargs["transport"] = self._transport
            if bool_has_value(self.jina_username):
                client_kwargs["auth"] = (self.jina_username, self.jina_token)
            else:
                headers["Authorization"] = f"Bearer {self.jina_token}"

            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(
                    "/rest/api/3/search",
                    params=(
                        ("jql", bounded_jql),
                        ("maxResults", str(bounded_limit)),
                        ("fields", "summary,description,status,assignee,created"),
                    ),
                )
                response.raise_for_status()
                return response.json()

        payload: dict[str, Any] = await self._retry_with_backoff(_fetch)

        issues: list[JinaIssue] = []
        for raw in payload.get("issues", []):
            fields = raw.get("fields", {})
            assignee = fields.get("assignee") or {}
            issue = JinaIssue(
                key=str(raw.get("key", "")).strip(),
                title=str(fields.get("summary", "")).strip(),
                description=flatten_description(fields.get("description")),
                status=str((fields.get("status") or {}).get("name", "Unknown")).strip()
                or "Unknown",
                assignee=str(assignee.get("displayName", "")).strip() or None,
                created_at=parse_timestamp(fields.get("created")),
                url=f"{self.jina_url}/browse/{raw.get('key', '')}",
            )
            if issue.key:
                issues.append(issue)
        return issues

    async def fetch_issue(self, issue_key: str) -> JinaIssue | None:
        import re

        clean = issue_key.strip().upper()
        if not re.match(r"^[A-Z][A-Z0-9]{1,9}-\d{1,6}$", clean):
            raise ValueError(f"Invalid issue key: {issue_key!r}")
        issues = await self.fetch_issues(
            jql=f'key = "{clean}"',
            limit=1,
        )
        return issues[0] if issues else None

    async def sync_issues(
        self,
        issues: list[JinaIssue],
        *,
        project_id: str | None = None,
    ) -> list[JinaIssue]:
        for issue in issues:
            await self.upsert_issue(issue, project_id=project_id)
        return issues

    async def find_code_for_issue(
        self,
        issue: JinaIssue,
        *,
        root: Path,
        project_id: str | None,
        threshold: float | None,
        limit: int,
        force_refresh: bool,
    ) -> list[CodeMatch]:
        indexed_files = await self._code_service.ensure_code_index(
            root,
            project_id=project_id,
            force_refresh=force_refresh,
        )
        issue_embedding = await self._embeddings_code_query(issue.as_embedding_text())
        await self.upsert_issue(issue, project_id=project_id)
        minimum_score = threshold if threshold is not None else self.match_threshold
        scored: list[CodeMatch] = []
        for record in indexed_files:
            score = cosine_similarity(issue_embedding, record.embedding)
            if issue.key.lower() in record.content.lower():
                score += 0.04
            if score < minimum_score:
                continue
            relation = "IMPLEMENTS" if score >= minimum_score + 0.08 else "MENTIONS"
            scored.append(
                CodeMatch(
                    file_id=record.file_id,
                    file_path=record.relative_path,
                    absolute_path=record.absolute_path,
                    language=record.language,
                    score=round(min(score, 1.0), 4),
                    relation=relation,
                    snippet=extract_snippet(issue, record.content),
                )
            )
        scored.sort(key=lambda item: (-item.score, item.file_path))
        results = scored[: max(1, limit)]
        for match in results:
            self.persist_issue_link(issue.issue_id(), match)
        return results

    async def find_tickets_for_file(
        self,
        file_path: str,
        *,
        root: Path,
        project_id: str | None,
        threshold: float | None,
        limit: int,
        include_resolved: bool,
    ) -> list[TicketMatch]:
        resolved_path = Path(file_path)
        if not resolved_path.is_absolute():
            resolved_path = (root / file_path).resolve()
        if not resolved_path.is_relative_to(root):
            raise ValueError(f"File path escapes the project root: {file_path!r}")
        if not resolved_path.exists() or not resolved_path.is_file():
            raise FileNotFoundError(f"File not found: {resolved_path}")

        indexed = await self._code_service.index_single_file(
            root,
            resolved_path,
            project_id=project_id,
        )
        if indexed is None:
            return []

        minimum_score = threshold if threshold is not None else self.match_threshold
        matches: list[TicketMatch] = []
        for issue, issue_embedding in self.load_stored_issues(
            project_id=project_id,
            include_resolved=include_resolved,
        ):
            score = cosine_similarity(indexed.embedding, issue_embedding)
            relation = (
                self.load_relation(issue.issue_id(), indexed.file_id) or "MENTIONS"
            )
            if relation == "IMPLEMENTS":
                score += 0.03
            if score < minimum_score:
                continue
            matches.append(
                TicketMatch(
                    issue_id=issue.issue_id(),
                    key=issue.key,
                    title=issue.title,
                    status=issue.status,
                    assignee=issue.assignee,
                    url=issue.url,
                    score=round(min(score, 1.0), 4),
                    relation=relation,
                )
            )
        matches.sort(key=lambda item: (-item.score, item.key))
        return matches[: max(1, limit)]

    def require_configuration(self) -> None:
        if self.configured:
            return
        raise JinaConfigurationError(
            "Jina integration is not configured. Set JINA_URL plus JINA_TOKEN, "
            "and optionally JINA_USERNAME for Basic auth."
        )

    async def upsert_issue(self, issue: JinaIssue, *, project_id: str | None) -> None:
        issue_id = issue.issue_id()
        source_hash = hashlib.sha256(
            issue.as_embedding_text().encode("utf-8")
        ).hexdigest()
        existing = rows(
            "MATCH (j:JinaIssue {id: $id}) RETURN j.source_hash LIMIT 1",
            {"id": issue_id},
        )
        ts = now_utc()
        embedding = await self._embeddings_code(issue.as_embedding_text())
        conn = db_get_connection()
        if not existing:
            conn.execute(
                """
                CREATE (j:JinaIssue {
                    id: $id,
                    issue_key: $issue_key,
                    title: $title,
                    description: $description,
                    status: $status,
                    assignee: $assignee,
                    url: $url,
                    source_hash: $source_hash,
                    embedding: $embedding,
                    created_at: $created_at,
                    synced_at: $ts
                })
                """,
                {
                    "id": issue_id,
                    "issue_key": issue.key,
                    "title": issue.title,
                    "description": issue.description,
                    "status": issue.status,
                    "assignee": issue.assignee,
                    "url": issue.url,
                    "source_hash": source_hash,
                    "embedding": embedding,
                    "created_at": issue.created_at,
                    "ts": ts,
                },
            )
        else:
            previous_hash = str(existing[0][0] or "")
            conn.execute(
                """
                MATCH (j:JinaIssue {id: $id})
                SET j.issue_key = $issue_key,
                    j.title = $title,
                    j.description = $description,
                    j.status = $status,
                    j.assignee = $assignee,
                    j.url = $url,
                    j.source_hash = $source_hash,
                    j.created_at = $created_at,
                    j.synced_at = $ts
                """,
                {
                    "id": issue_id,
                    "issue_key": issue.key,
                    "title": issue.title,
                    "description": issue.description,
                    "status": issue.status,
                    "assignee": issue.assignee,
                    "url": issue.url,
                    "source_hash": source_hash,
                    "created_at": issue.created_at,
                    "ts": ts,
                },
            )
            if previous_hash != source_hash:
                await db_update_embedding(
                    "JinaIssue",
                    issue_id,
                    embedding,
                    "idx_jina_issue_emb",
                )

        if project_id:
            ensure_project_link(project_id, issue_id, "JinaIssue", "HAS_JINA_ISSUE")

    def persist_issue_link(self, issue_id: str, match: CodeMatch) -> None:
        if self.load_relation(issue_id, match.file_id) is not None:
            return
        import re

        # Validate relation to prevent injection
        identifier_pattern = r"^[a-zA-Z_][\w]*$"
        if not re.match(identifier_pattern, match.relation):
            raise ValueError(f"Invalid relation: {match.relation}")

        db_get_connection().execute(  # nosemgrep
            f"""
            MATCH (j:JinaIssue {{id: $issue_id}}), (f:CodeFile {{id: $file_id}})
            CREATE (j)-[:{match.relation} {{score: $score, snippet: $snippet, linked_at: $ts}}]->(f)
            """,
            {
                "issue_id": issue_id,
                "file_id": match.file_id,
                "score": match.score,
                "snippet": match.snippet,
                "ts": now_utc(),
            },
        )

    def load_relation(self, issue_id: str, file_id: str) -> str | None:
        for relation in ("IMPLEMENTS", "MENTIONS"):
            result_rows = rows(  # nosemgrep
                f"""
                MATCH (:JinaIssue {{id: $issue_id}})-[:{relation}]->(:CodeFile {{id: $file_id}})
                RETURN count(*)
                """,
                {"issue_id": issue_id, "file_id": file_id},
            )
            if result_rows and int(result_rows[0][0]) > 0:
                return relation
        return None

    def load_stored_issues(
        self,
        *,
        project_id: str | None,
        include_resolved: bool,
    ) -> list[tuple[JinaIssue, list[float]]]:
        issues: list[tuple[JinaIssue, list[float]]] = []
        for row in self.query_stored_issue_rows(project_id):
            issue_record = self.stored_issue_from_row(row)
            if issue_record is None:
                continue
            issue, embedding = issue_record
            if not include_resolved and issue.status.lower() in DONE_STATUSES:
                continue
            issues.append((issue, embedding))
        return issues

    def query_stored_issue_rows(self, project_id: str | None) -> list[list[Any]]:
        if project_id:
            return rows(
                """
                MATCH (p:Project {id: $project_id})-[:HAS_JINA_ISSUE]->(j:JinaIssue)
                RETURN j.issue_key, j.title, j.description, j.status, j.assignee, j.created_at, j.url, j.embedding
                ORDER BY j.synced_at DESC
                """,
                {"project_id": project_id},
            )
        return rows(
            """
            MATCH (j:JinaIssue)
            RETURN j.issue_key, j.title, j.description, j.status, j.assignee, j.created_at, j.url, j.embedding
            ORDER BY j.synced_at DESC
            """
        )

    def stored_issue_from_row(
        self, row: list[Any]
    ) -> tuple[JinaIssue, list[float]] | None:
        issue_key = str(row[0] or "")
        embedding = [float(value) for value in cast(list[float], row[7] or [])]
        if not issue_key or not embedding:
            return None
        issue = JinaIssue(
            key=issue_key,
            title=str(row[1] or ""),
            description=str(row[2] or ""),
            status=str(row[3] or "Unknown"),
            assignee=str(row[4]).strip() or None if row[4] is not None else None,
            created_at=row[5],
            url=str(row[6] or ""),
        )
        return issue, embedding
