"""Code file indexing and persistence for Jina semantic linking."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from ..config import FILE_TREE_DEFAULT_ROOT
from ..db import db_get_connection, db_update_embedding
from .jina_common import (
    CODE_EXTENSIONS,
    MAX_FILE_BYTES,
    MAX_FILE_CHARS,
    SKIP_DIRS,
    IndexedCodeFile,
    code_file_id,
    language_for_path,
    now_utc,
    summarize_content,
)

EmbeddingFn = Callable[[str], Awaitable[list[float]]]


def rows(query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    result = db_get_connection().execute(query, params or {})
    if isinstance(result, list):
        result = result[0]
    return cast(list[list[Any]], result.get_all())


class CodeEmbedService:
    """Index local source files and persist CodeFile nodes."""

    def __init__(self, *, embeddings_code: EmbeddingFn) -> None:
        self._embeddings_code = embeddings_code
        self.indexed_root: str | None = None
        self.indexed_files: dict[str, IndexedCodeFile] = {}
        self.loaded_at: datetime | None = None
        self.last_used_at: datetime | None = None

    def resolve_root_path(
        self,
        *,
        root_path: str | None = None,
        project_id: str | None = None,
    ) -> Path:
        candidate = root_path or self.project_root(project_id) or FILE_TREE_DEFAULT_ROOT or os.getcwd()
        root = Path(candidate).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Root path does not exist or is not a directory: {root}")
        return root

    def project_root(self, project_id: str | None) -> str | None:
        if not project_id:
            return None
        result_rows = rows(
            "MATCH (p:Project {id: $project_id}) RETURN p.repo_path LIMIT 1",
            {"project_id": project_id},
        )
        if not result_rows:
            return None
        repo_path = result_rows[0][0]
        return str(repo_path) if repo_path else None

    async def ensure_code_index(
        self,
        root: Path,
        *,
        project_id: str | None,
        force_refresh: bool,
    ) -> list[IndexedCodeFile]:
        if not force_refresh and self.indexed_root == str(root) and self.indexed_files:
            self.last_used_at = now_utc()
            return list(self.indexed_files.values())

        indexed_files: dict[str, IndexedCodeFile] = {}
        for path in self.iter_code_files(root):
            record = await self.index_single_file(root, path, project_id=project_id)
            if record is not None:
                indexed_files[record.file_id] = record

        self.indexed_root = str(root)
        self.indexed_files = indexed_files
        self.loaded_at = now_utc()
        self.last_used_at = self.loaded_at
        return list(indexed_files.values())

    async def index_single_file(
        self,
        root: Path,
        path: Path,
        *,
        project_id: str | None,
    ) -> IndexedCodeFile | None:
        text, size_bytes = self.read_text_file(path)
        if not text:
            return None
        relative_path = path.resolve().relative_to(root).as_posix()
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        record = IndexedCodeFile(
            file_id=code_file_id(relative_path),
            absolute_path=str(path.resolve()),
            relative_path=relative_path,
            language=language_for_path(path),
            size_bytes=size_bytes,
            content_hash=content_hash,
            summary=summarize_content(text),
            content=text,
            embedding=await self._embeddings_code(text),
        )
        await self.upsert_code_file(record, project_id=project_id)
        self.last_used_at = now_utc()
        self.indexed_files[record.file_id] = record
        return record

    def iter_code_files(self, root: Path) -> list[Path]:
        files: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                name
                for name in dirnames
                if not name.startswith(".") and name not in SKIP_DIRS
            ]
            current_dir = Path(dirpath)
            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue
                path = current_dir / filename
                if path.is_symlink() or path.suffix.lower() not in CODE_EXTENSIONS:
                    continue
                files.append(path)
        return files

    def read_text_file(self, path: Path) -> tuple[str, int]:
        try:
            raw = path.read_bytes()
        except OSError:
            return "", 0
        if b"\x00" in raw[:4096]:
            return "", 0
        size_bytes = len(raw)
        text = raw[:MAX_FILE_BYTES].decode("utf-8", errors="replace")
        return text[:MAX_FILE_CHARS], size_bytes

    async def upsert_code_file(
        self,
        record: IndexedCodeFile,
        *,
        project_id: str | None,
    ) -> None:
        existing = rows(
            "MATCH (f:CodeFile {id: $id}) RETURN f.content_hash LIMIT 1",
            {"id": record.file_id},
        )
        ts = now_utc()
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
                await db_update_embedding(
                    "CodeFile",
                    record.file_id,
                    record.embedding,
                    "idx_codefile_emb",
                )

        if project_id:
            ensure_project_link(project_id, record.file_id, "CodeFile", "HAS_FILE")


def ensure_project_link(project_id: str, node_id: str, label: str, rel_name: str) -> None:
    result_rows = rows(
        f"""
        MATCH (:Project {{id: $project_id}})-[:{rel_name}]->(:{label} {{id: $node_id}})
        RETURN count(*)
        """,
        {"project_id": project_id, "node_id": node_id},
    )
    if result_rows and int(result_rows[0][0]) > 0:
        return
    db_get_connection().execute(
        f"""
        MATCH (p:Project {{id: $project_id}}), (n:{label} {{id: $node_id}})
        CREATE (p)-[:{rel_name}]->(n)
        """,
        {"project_id": project_id, "node_id": node_id},
    )
