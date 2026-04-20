#!/usr/bin/env python3
"""Facade for Jina issue ingestion and ticket-to-code semantic linking."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from ...config import (
    JINA_EMBEDDER_TTL_SECONDS,
    JINA_MATCH_THRESHOLD,
    JINA_MAX_RESULTS,
    JINA_PROJECT_KEY,
    JINA_TOKEN,
    JINA_URL,
    JINA_USERNAME,
)
from ...embeddings import embeddings_code, embeddings_code_query
from .code_embed_service import CodeEmbedService
from ..embed_client import EmbedClientBase
from .jina_common import (
    CodeMatch,
    IndexedCodeFile,
    JinaConfigurationError,
    JinaIssue,
    TicketMatch,
    bool_has_value,
    code_file_id,
    jina_issue_id,
    now_utc,
)
from .text_embed_service import TextEmbedService

logger = logging.getLogger(__name__)


class JinaCodeEmbedder(EmbedClientBase):
    """Coordinate Jina issue ingestion, code indexing, and semantic matching."""

    def __init__(
        self,
        *,
        jina_url: str | None = None,
        jina_username: str | None = None,
        jina_token: str | None = None,
        project_key: str | None = None,
        match_threshold: float = JINA_MATCH_THRESHOLD,
        max_results: int = JINA_MAX_RESULTS,
        ttl_seconds: int = JINA_EMBEDDER_TTL_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(model="jina-code")
        self.jina_url = (jina_url or JINA_URL).rstrip("/")
        self.jina_username = jina_username or JINA_USERNAME
        self.jina_token = jina_token or JINA_TOKEN
        self.project_key = project_key or JINA_PROJECT_KEY
        self.match_threshold = match_threshold
        self.max_results = max(1, max_results)
        self.ttl_seconds = max(30, ttl_seconds)
        self._code_service = CodeEmbedService(embeddings_code=embeddings_code)
        self._text_service = TextEmbedService(
            jina_url=self.jina_url,
            jina_username=self.jina_username,
            jina_token=self.jina_token,
            project_key=self.project_key,
            match_threshold=self.match_threshold,
            max_results=self.max_results,
            transport=transport,
            code_service=self._code_service,
            embeddings_code=embeddings_code,
            embeddings_code_query=embeddings_code_query,
        )

    @property
    def configured(self) -> bool:
        return bool_has_value(self.jina_url) and bool_has_value(self.jina_token)

    @property
    def index_loaded(self) -> bool:
        return bool(self._code_service.indexed_files)

    @property
    def indexed_file_count(self) -> int:
        return len(self._code_service.indexed_files)

    @property
    def _indexed_files(self) -> dict[str, IndexedCodeFile]:
        return self._code_service.indexed_files

    @property
    def _indexed_root(self) -> str | None:
        return self._code_service.indexed_root

    @property
    def _last_used_at(self) -> datetime | None:
        return self._code_service.last_used_at

    def default_jql(self) -> str:
        return self._text_service.default_jql()

    def release_idle_resources(self, *, now: datetime | None = None) -> bool:
        if (
            not self._code_service.indexed_files
            or self._code_service.last_used_at is None
        ):
            return False
        current = now or now_utc()
        if current - self._code_service.last_used_at < timedelta(
            seconds=self.ttl_seconds
        ):
            return False
        logger.info(
            "jina_embedder_unloaded root=%s files=%s",
            self._code_service.indexed_root,
            len(self._code_service.indexed_files),
        )
        self._code_service.indexed_files.clear()
        self._code_service.indexed_root = None
        self._code_service.loaded_at = None
        self._code_service.last_used_at = None
        return True

    async def fetch_issues(
        self,
        *,
        jql: str | None = None,
        limit: int | None = None,
    ) -> list[JinaIssue]:
        return await self._text_service.fetch_issues(jql=jql, limit=limit)

    async def fetch_issue(self, issue_key: str) -> JinaIssue | None:
        return await self._text_service.fetch_issue(issue_key)

    async def sync_issues(
        self,
        issues: list[JinaIssue],
        *,
        project_id: str | None = None,
    ) -> list[JinaIssue]:
        return await self._text_service.sync_issues(issues, project_id=project_id)

    async def find_code_for_issue(
        self,
        issue: JinaIssue,
        *,
        root_path: str | None = None,
        project_id: str | None = None,
        threshold: float | None = None,
        limit: int = 5,
        force_refresh: bool = False,
    ) -> list[CodeMatch]:
        self.release_idle_resources()
        root = self.resolve_root_path(root_path=root_path, project_id=project_id)
        results = await self._text_service.find_code_for_issue(
            issue,
            root=root,
            project_id=project_id,
            threshold=threshold,
            limit=limit,
            force_refresh=force_refresh,
        )
        logger.info(
            "jina_embedder_loaded root=%s files=%s",
            root,
            len(self._code_service.indexed_files),
        )
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
        return await self._text_service.find_tickets_for_file(
            file_path,
            root=root,
            project_id=project_id,
            threshold=threshold,
            limit=limit,
            include_resolved=include_resolved,
        )

    def resolve_root_path(
        self,
        *,
        root_path: str | None = None,
        project_id: str | None = None,
    ) -> Path:
        return self._code_service.resolve_root_path(
            root_path=root_path,
            project_id=project_id,
        )


_jina_embedder: JinaCodeEmbedder | None = None


def get_jina_embedder(
    *,
    force_reload: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> JinaCodeEmbedder:
    """Return the process-wide Jina embedder instance."""
    global _jina_embedder
    if _jina_embedder is None or force_reload:
        _jina_embedder = JinaCodeEmbedder(transport=transport)
    return _jina_embedder


def reset_jina_embedder() -> None:
    """Clear the process-wide Jina embedder cache, mainly for tests."""
    global _jina_embedder
    _jina_embedder = None


__all__ = [
    "CodeMatch",
    "IndexedCodeFile",
    "JinaCodeEmbedder",
    "JinaConfigurationError",
    "JinaIssue",
    "TicketMatch",
    "code_file_id",
    "embeddings_code",
    "embeddings_code_query",
    "get_jina_embedder",
    "jina_issue_id",
    "reset_jina_embedder",
]
