#!/usr/bin/env python3
"""Jira issue ingestion and ticket-to-code semantic linking."""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import BaseModel, Field

from ..config import (
    FILE_TREE_DEFAULT_ROOT,
    JIRA_EMBEDDER_TTL_SECONDS,
    JIRA_MATCH_THRESHOLD,
    JIRA_MAX_RESULTS,
    JIRA_PROJECT_KEY,
    JIRA_TOKEN,
    JIRA_URL,
    JIRA_USERNAME,
)
from ..db import db_get_connection, db_update_embedding
from ..embeddings import embeddings_code, embeddings_code_query

m = hashlib.sha256()

logger = logging.getLogger(__name__)

_CODE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
_SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
_MAX_FILE_BYTES = 64_000
_MAX_FILE_CHARS = 8_000
_DEFAULT_TIMEOUT_SECONDS = 15.0
_DONE_STATUSES = {"closed", "done", "resolved"}
_LANGUAGE_BY_SUFFIX = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".md": "markdown",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sql": "sql",
    ".swift": "swift",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".yaml": "yaml",
    ".yml": "yaml",
}


class JiraConfigurationError(RuntimeError):
    """Raised when Jira access is requested without the required configuration."""


class JiraIssue(BaseModel):
    """A Jira issue payload normalized for semantic matching."""

    key: str = Field(description="Issue key, for example MEM-42.")
    title: str = Field(description="Short Jira issue summary.")
    description: str = Field(default="", description="Flattened issue description.")
    status: str = Field(default="Unknown", description="Current Jira workflow state.")
    assignee: str | None = Field(default=None, description="Display name of the current assignee.")
    created_at: datetime | None = Field(default=None, description="Original creation timestamp.")
    url: str = Field(description="Browsable issue URL.")

    def issue_id(self) -> str:
        return jira_issue_id(self.key)

    def as_embedding_text(self) -> str:
        return f"{self.key}\n{self.title}\n{self.description}".strip()


class CodeMatch(BaseModel):
    """A semantic match between a Jira issue and a code file."""

    file_id: str
    file_path: str
    absolute_path: str
    language: str
    score: float
    relation: str
    snippet: str


class TicketMatch(BaseModel):
    """A semantic match between a code file and a Jira issue."""

    issue_id: str
    key: str
    title: str
    status: str
    assignee: str | None = None
    url: str
    score: float
    relation: str


@dataclass(slots=True)
class IndexedCodeFile:
    """In-memory representation of an indexed file used for scoring and snippets."""

    file_id: str
    absolute_path: str
    relative_path: str
    language: str
    size_bytes: int
    content_hash: str
    summary: str
    content: str
    embedding: list[float]


def jira_issue_id(issue_key: str) -> str:
    return f"jira:{issue_key.strip().upper()}"


def code_file_id(relative_path: str) -> str:
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]
    return f"codefile:{digest}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rows(query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    conn = db_get_connection()
    result = conn.execute(query, params or {})
    if isinstance(result, list):
        result = result[0]
    return cast(list[list[Any]], result.get_all())


def _bool_has_value(value: str | None) -> bool:
    return bool(value and value.strip())


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _flatten_description(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(part for part in (_flatten_description(item) for item in value) if part)
    if isinstance(value, dict):
        node_type = str(value.get("type", ""))
        if node_type == "text":
            return str(value.get("text", ""))
        if node_type == "hardBreak":
            return "\n"
        content = _flatten_description(value.get("content"))
        if node_type in {"paragraph", "heading", "bulletList", "orderedList", "listItem"}:
            return content.strip()
        return content.strip()
    return str(value).strip()


def _language_for_path(path: Path) -> str:
    return _LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "text")


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _summarize_content(content: str) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return " ".join(lines[:3])[:220]


def _extract_snippet(issue: JiraIssue, content: str, *, context_lines: int = 3) -> str:
    tokens = {
        token.lower()
        for token in (issue.title + " " + issue.description).replace("-", " ").split()
        if len(token) >= 4
    }
    lines = content.splitlines()
    for index, line in enumerate(lines):
        lowered = line.lower()
        if any(token in lowered for token in tokens):
            start = max(0, index - context_lines)
            end = min(len(lines), index + context_lines + 1)
            return "\n".join(lines[start:end]).strip()
    return "\n".join(lines[: min(len(lines), context_lines * 2 + 1)]).strip()


class JiraCodeEmbedder:
    """Read-only Jira integration with lazy code indexing and graph persistence."""

    def __init__(
        self,
        *,
        jira_url: str | None = None,
        jira_username: str | None = None,
        jira_token: str | None = None,
        project_key: str | None = None,
        match_threshold: float = JIRA_MATCH_THRESHOLD,
        max_results: int = JIRA_MAX_RESULTS,
        ttl_seconds: int = JIRA_EMBEDDER_TTL_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.jira_url = (jira_url or JIRA_URL).rstrip("/")
        self.jira_username = jira_username or JIRA_USERNAME
        self.jira_token = jira_token or JIRA_TOKEN
        self.project_key = project_key or JIRA_PROJECT_KEY
        self.match_threshold = match_threshold
        self.max_results = max(1, max_results)
        self.ttl_seconds = max(30, ttl_seconds)
        self._transport = transport
        self._indexed_root: str | None = None
        self._indexed_files: dict[str, IndexedCodeFile] = {}
        self._loaded_at: datetime | None = None
        self._last_used_at: datetime | None = None

    @property
    def configured(self) -> bool:
        return _bool_has_value(self.jira_url) and _bool_has_value(self.jira_token)

    @property
    def index_loaded(self) -> bool:
        return bool(self._indexed_files)

    @property
    def indexed_file_count(self) -> int:
        return len(self._indexed_files)

    def default_jql(self) -> str:
        if _bool_has_value(self.project_key):
            return f"project = {self.project_key} ORDER BY updated DESC"
        return "updated >= -30d ORDER BY updated DESC"

    def release_idle_resources(self, *, now: datetime | None = None) -> bool:
        if not self._indexed_files or self._last_used_at is None:
            return False

        current = now or _now()
        if current - self._last_used_at < timedelta(seconds=self.ttl_seconds):
            return False

        logger.info("jira_embedder_unloaded root=%s files=%s", self._indexed_root, len(self._indexed_files))
        self._indexed_files.clear()
        self._indexed_root = None
        self._loaded_at = None
        self._last_used_at = None
        return True

    async def fetch_issues(self, *, jql: str | None = None, limit: int | None = None) -> list[JiraIssue]:
        self._require_configuration()
        bounded_limit = min(max(limit or self.max_results, 1), self.max_results)
        bounded_jql = (jql or self.default_jql()).strip()
        if len(bounded_jql) > 500:
            raise ValueError("JQL must be 500 characters or fewer.")

        params: tuple[tuple[str, str | int | float | bool | None], ...] = (
            ("jql", bounded_jql),
            ("maxResults", str(bounded_limit)),
            ("fields", "summary,description,status,assignee,created"),
        )
        headers = {"Accept": "application/json"}
        client_kwargs: dict[str, Any] = {
            "base_url": self.jira_url,
            "headers": headers,
            "timeout": _DEFAULT_TIMEOUT_SECONDS,
        }
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        if _bool_has_value(self.jira_username):
            client_kwargs["auth"] = (self.jira_username, self.jira_token)
        else:
            headers["Authorization"] = f"Bearer {self.jira_token}"

        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.get("/rest/api/3/search", params=params)
            response.raise_for_status()
            payload = response.json()

        issues: list[JiraIssue] = []
        for raw in payload.get("issues", []):
            fields = raw.get("fields", {})
            assignee = fields.get("assignee") or {}
            issue = JiraIssue(
                key=str(raw.get("key", "")).strip(),
                title=str(fields.get("summary", "")).strip(),
                description=_flatten_description(fields.get("description")),
                status=str((fields.get("status") or {}).get("name", "Unknown")).strip() or "Unknown",
                assignee=str(assignee.get("displayName", "")).strip() or None,
                created_at=_parse_timestamp(fields.get("created")),
                url=f"{self.jira_url}/browse/{raw.get('key', '')}",
            )
            if issue.key:
                issues.append(issue)
        return issues

    async def fetch_issue(self, issue_key: str) -> JiraIssue | None:
        issues = await self.fetch_issues(jql=f"key = {issue_key.strip().upper()}", limit=1)
        return issues[0] if issues else None

    async def sync_issues(self, issues: list[JiraIssue], *, project_id: str | None = None) -> list[JiraIssue]:
        for issue in issues:
            await self._upsert_issue(issue, project_id=project_id)
        return issues

    async def find_code_for_issue(
        self,
        issue: JiraIssue,
        *,
        root_path: str | None = None,
        project_id: str | None = None,
        threshold: float | None = None,
        limit: int = 5,
        force_refresh: bool = False,
    ) -> list[CodeMatch]:
        root = self.resolve_root_path(root_path=root_path, project_id=project_id)
        indexed_files = await self._ensure_code_index(root, project_id=project_id, force_refresh=force_refresh)
        issue_embedding = await embeddings_code_query(issue.as_embedding_text())
        await self._upsert_issue(issue, project_id=project_id)

        minimum_score = threshold if threshold is not None else self.match_threshold
        scored: list[CodeMatch] = []
        for record in indexed_files:
            score = _cosine_similarity(issue_embedding, record.embedding)
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
                    snippet=_extract_snippet(issue, record.content),
                )
            )

        scored.sort(key=lambda item: (-item.score, item.file_path))
        results = scored[: max(1, limit)]
        for match in results:
            self._persist_issue_link(issue.issue_id(), match)
        return results

    async def find_tickets_for_file(
        self,
        file_path: str,
        *,
        root_path: str | None = None,
        project_id: str | None = None,
        threshold: float | None = None,
        limit: int = 5,
        include_resolved: bool = True,
    ) -> list[TicketMatch]:
        root = self.resolve_root_path(root_path=root_path, project_id=project_id)
        resolved_path = Path(file_path)
        if not resolved_path.is_absolute():
            resolved_path = (root / file_path).resolve()
        if not resolved_path.exists() or not resolved_path.is_file():
            raise FileNotFoundError(f"File not found: {resolved_path}")

        indexed = await self._index_single_file(root, resolved_path, project_id=project_id)
        if indexed is None:
            return []

        minimum_score = threshold if threshold is not None else self.match_threshold
        matches: list[TicketMatch] = []
        for issue, persisted_relation in self._load_stored_issues(project_id=project_id, include_resolved=include_resolved):
            score = _cosine_similarity(indexed.embedding, persisted_relation)
            relation = self._load_relation(issue.issue_id(), indexed.file_id) or "MENTIONS"
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

    def resolve_root_path(self, *, root_path: str | None = None, project_id: str | None = None) -> Path:
        candidate = root_path or self._project_root(project_id) or FILE_TREE_DEFAULT_ROOT or os.getcwd()
        root = Path(candidate).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Root path does not exist or is not a directory: {root}")
        return root

    def _require_configuration(self) -> None:
        if self.configured:
            return
        raise JiraConfigurationError(
            "Jira integration is not configured. Set JIRA_URL plus JIRA_TOKEN, and optionally JIRA_USERNAME for Basic auth."
        )

    def _project_root(self, project_id: str | None) -> str | None:
        if not project_id:
            return None
        rows = _rows(
            "MATCH (p:Project {id: $project_id}) RETURN p.repo_path LIMIT 1",
            {"project_id": project_id},
        )
        if not rows:
            return None
        repo_path = rows[0][0]
        return str(repo_path) if repo_path else None

    async def _ensure_code_index(
        self,
        root: Path,
        *,
        project_id: str | None,
        force_refresh: bool,
    ) -> list[IndexedCodeFile]:
        self.release_idle_resources()

        if not force_refresh and self._indexed_root == str(root) and self._indexed_files:
            self._last_used_at = _now()
            return list(self._indexed_files.values())

        indexed_files: dict[str, IndexedCodeFile] = {}
        for path in self._iter_code_files(root):
            record = await self._index_single_file(root, path, project_id=project_id)
            if record is None:
                continue
            indexed_files[record.file_id] = record

        self._indexed_root = str(root)
        self._indexed_files = indexed_files
        self._loaded_at = _now()
        self._last_used_at = self._loaded_at
        logger.info("jira_embedder_loaded root=%s files=%s", root, len(indexed_files))
        return list(indexed_files.values())

    async def _index_single_file(
        self,
        root: Path,
        path: Path,
        *,
        project_id: str | None,
    ) -> IndexedCodeFile | None:
        text, size_bytes = self._read_text_file(path)
        if not text:
            return None
        relative_path = path.resolve().relative_to(root).as_posix()
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        record = IndexedCodeFile(
            file_id=code_file_id(relative_path),
            absolute_path=str(path.resolve()),
            relative_path=relative_path,
            language=_language_for_path(path),
            size_bytes=size_bytes,
            content_hash=content_hash,
            summary=_summarize_content(text),
            content=text,
            embedding=await embeddings_code(text),
        )
        await self._upsert_code_file(record, project_id=project_id)
        self._last_used_at = _now()
        self._indexed_files[record.file_id] = record
        return record

    def _iter_code_files(self, root: Path) -> list[Path]:
        files: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                name
                for name in dirnames
                if not name.startswith(".") and name not in _SKIP_DIRS
            ]
            current_dir = Path(dirpath)
            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue
                path = current_dir / filename
                if path.is_symlink() or path.suffix.lower() not in _CODE_EXTENSIONS:
                    continue
                files.append(path)
        return files

    def _read_text_file(self, path: Path) -> tuple[str, int]:
        try:
            raw = path.read_bytes()
        except OSError:
            return "", 0
        if b"\x00" in raw[:4096]:
            return "", 0
        size_bytes = len(raw)
        text = raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
        return text[:_MAX_FILE_CHARS], size_bytes

    async def _upsert_code_file(self, record: IndexedCodeFile, *, project_id: str | None) -> None:
        existing = _rows(
            "MATCH (f:CodeFile {id: $id}) RETURN f.content_hash LIMIT 1",
            {"id": record.file_id},
        )
        ts = _now()
        conn = db_get_connection()

        if not existing:
            conn.execute(
                """
                CREATE (f:CodeFile {
                    id: $id,
                    path: $path,
                    name: $name,
                    language: $language,
                    size_bytes: $size_bytes,
                    content_hash: $content_hash,
                    summary: $summary,
                    embedding: $embedding,
                    indexed_at: $ts,
                    updated_at: $ts
                })
                """,
                {
                    "id": record.file_id,
                    "path": record.relative_path,
                    "name": Path(record.relative_path).name,
                    "language": record.language,
                    "size_bytes": record.size_bytes,
                    "content_hash": record.content_hash,
                    "summary": record.summary,
                    "embedding": record.embedding,
                    "ts": ts,
                },
            )
        else:
            previous_hash = str(existing[0][0] or "")
            conn.execute(
                """
                MATCH (f:CodeFile {id: $id})
                SET f.path = $path,
                    f.name = $name,
                    f.language = $language,
                    f.size_bytes = $size_bytes,
                    f.content_hash = $content_hash,
                    f.summary = $summary,
                    f.updated_at = $ts,
                    f.indexed_at = CASE WHEN $content_changed THEN $ts ELSE f.indexed_at END
                """,
                {
                    "id": record.file_id,
                    "path": record.relative_path,
                    "name": Path(record.relative_path).name,
                    "language": record.language,
                    "size_bytes": record.size_bytes,
                    "content_hash": record.content_hash,
                    "summary": record.summary,
                    "ts": ts,
                    "content_changed": previous_hash != record.content_hash,
                },
            )
            if previous_hash != record.content_hash:
                await db_update_embedding("CodeFile", record.file_id, record.embedding, "idx_codefile_emb")

        if project_id:
            self._ensure_project_link(project_id, record.file_id, "CodeFile", "HAS_FILE")

    async def _upsert_issue(self, issue: JiraIssue, *, project_id: str | None) -> None:
        issue_id = issue.issue_id()
        source_hash = hashlib.sha256(issue.as_embedding_text().encode("utf-8")).hexdigest()
        existing = _rows(
            "MATCH (j:JiraIssue {id: $id}) RETURN j.source_hash LIMIT 1",
            {"id": issue_id},
        )
        ts = _now()
        embedding = await embeddings_code(issue.as_embedding_text())
        conn = db_get_connection()

        if not existing:
            conn.execute(
                """
                CREATE (j:JiraIssue {
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
                MATCH (j:JiraIssue {id: $id})
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
                await db_update_embedding("JiraIssue", issue_id, embedding, "idx_jira_issue_emb")

        if project_id:
            self._ensure_project_link(project_id, issue_id, "JiraIssue", "HAS_JIRA_ISSUE")

    def _ensure_project_link(self, project_id: str, node_id: str, label: str, rel_name: str) -> None:
        rows = _rows(
            f"""
            MATCH (:Project {{id: $project_id}})-[:{rel_name}]->(:{label} {{id: $node_id}})
            RETURN count(*)
            """,
            {"project_id": project_id, "node_id": node_id},
        )
        if rows and int(rows[0][0]) > 0:
            return
        conn = db_get_connection()
        conn.execute(
            f"""
            MATCH (p:Project {{id: $project_id}}), (n:{label} {{id: $node_id}})
            CREATE (p)-[:{rel_name}]->(n)
            """,
            {"project_id": project_id, "node_id": node_id},
        )

    def _persist_issue_link(self, issue_id: str, match: CodeMatch) -> None:
        if self._load_relation(issue_id, match.file_id) is not None:
            return
        conn = db_get_connection()
        conn.execute(
            f"""
            MATCH (j:JiraIssue {{id: $issue_id}}), (f:CodeFile {{id: $file_id}})
            CREATE (j)-[:{match.relation} {{score: $score, snippet: $snippet, linked_at: $ts}}]->(f)
            """,
            {
                "issue_id": issue_id,
                "file_id": match.file_id,
                "score": match.score,
                "snippet": match.snippet,
                "ts": _now(),
            },
        )

    def _load_relation(self, issue_id: str, file_id: str) -> str | None:
        for relation in ("IMPLEMENTS", "MENTIONS"):
            rows = _rows(
                f"""
                MATCH (:JiraIssue {{id: $issue_id}})-[:{relation}]->(:CodeFile {{id: $file_id}})
                RETURN count(*)
                """,
                {"issue_id": issue_id, "file_id": file_id},
            )
            if rows and int(rows[0][0]) > 0:
                return relation
        return None

    def _load_stored_issues(
        self,
        *,
        project_id: str | None,
        include_resolved: bool,
    ) -> list[tuple[JiraIssue, list[float]]]:
        rows = self._query_stored_issue_rows(project_id)
        issues: list[tuple[JiraIssue, list[float]]] = []
        for row in rows:
            issue_record = self._stored_issue_from_row(row)
            if issue_record is None:
                continue
            issue, embedding = issue_record
            if not include_resolved and issue.status.lower() in _DONE_STATUSES:
                continue
            issues.append((issue, embedding))
        return issues

    def _query_stored_issue_rows(self, project_id: str | None) -> list[list[Any]]:
        if project_id:
            return _rows(
                """
                MATCH (p:Project {id: $project_id})-[:HAS_JIRA_ISSUE]->(j:JiraIssue)
                RETURN j.issue_key, j.title, j.description, j.status, j.assignee, j.created_at, j.url, j.embedding
                ORDER BY j.synced_at DESC
                """,
                {"project_id": project_id},
            )
        return _rows(
            """
            MATCH (j:JiraIssue)
            RETURN j.issue_key, j.title, j.description, j.status, j.assignee, j.created_at, j.url, j.embedding
            ORDER BY j.synced_at DESC
            """
        )

    def _stored_issue_from_row(self, row: list[Any]) -> tuple[JiraIssue, list[float]] | None:
        issue_key = str(row[0] or "")
        embedding = [float(value) for value in cast(list[float], row[7] or [])]
        if not issue_key or not embedding:
            return None
        issue = JiraIssue(
            key=issue_key,
            title=str(row[1] or ""),
            description=str(row[2] or ""),
            status=str(row[3] or "Unknown"),
            assignee=str(row[4]).strip() or None if row[4] is not None else None,
            created_at=row[5],
            url=str(row[6] or ""),
        )
        return issue, embedding


_jira_embedder: JiraCodeEmbedder | None = None


def get_jira_embedder(
    *,
    force_reload: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> JiraCodeEmbedder:
    """Return the process-wide Jira embedder instance."""

    global _jira_embedder
    if _jira_embedder is None or force_reload:
        _jira_embedder = JiraCodeEmbedder(transport=transport)
    return _jira_embedder


def reset_jira_embedder() -> None:
    """Clear the process-wide Jira embedder cache, mainly for tests."""

    global _jira_embedder
    _jira_embedder = None