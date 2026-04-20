"""Embedding helpers reused by curated CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...embeddings import embeddings_code, embeddings_documents
from ...services.jina.code_embed_service import CodeEmbedService
from .base import failed, ok, resolve_root_path

_CMD_EMBED_DOCS = "embed documents"

async def embed_documents(
    *,
    texts: list[str] | None = None,
    files: list[str] | None = None,
    root: str | None = None,
    include_vectors: bool = False,
) -> dict[str, Any]:
    """Embed raw text values or text files using the configured document embedder."""
    payloads: list[tuple[str, str]] = []
    if texts:
        payloads.extend(
            (f"text:{index}", text) for index, text in enumerate(texts, start=1)
        )

    root_path = resolve_root_path(root)
    for file_name in files or []:
        candidate = Path(file_name)
        if not candidate.is_absolute():
            candidate = (root_path / candidate).resolve()
        if not candidate.exists() or not candidate.is_file():
            return failed(_CMD_EMBED_DOCS, f"File not found: {candidate}")
        payloads.append(
            (
                candidate.relative_to(root_path).as_posix(),
                candidate.read_text(encoding="utf-8"),
            )
        )

    if not payloads:
        return failed(
            _CMD_EMBED_DOCS, "Provide at least one text value or file path."
        )

    vectors = await embeddings_documents([text for _, text in payloads])
    items = []
    for index, (source, text) in enumerate(payloads):
        item: dict[str, Any] = {
            "source": source,
            "chars": len(text),
            "dimension": len(vectors[index]),
        }
        if include_vectors:
            item["embedding"] = vectors[index]
        items.append(item)
    return ok(_CMD_EMBED_DOCS, {"items": items})


async def embed_code(
    *,
    root: str | None = None,
    paths: list[str] | None = None,
    project_id: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Index code files through the existing code embedding service."""
    service = CodeEmbedService(embeddings_code=embeddings_code)
    root_path = service.resolve_root_path(root_path=root, project_id=project_id)
    records = []

    if paths:
        for file_name in paths:
            candidate = Path(file_name)
            if not candidate.is_absolute():
                candidate = (root_path / candidate).resolve()
            if not candidate.exists() or not candidate.is_file():
                return failed("embed code", f"File not found: {candidate}")
            record = await service.index_single_file(
                root_path, candidate, project_id=project_id
            )
            if record is not None:
                records.append(record)
    else:
        records = await service.ensure_code_index(
            root_path,
            project_id=project_id,
            force_refresh=force_refresh,
        )

    return ok(
        "embed code",
        {
            "root": str(root_path),
            "files_indexed": len(records),
            "files": [
                {
                    "file_id": record.file_id,
                    "path": record.relative_path,
                    "language": record.language,
                    "dimension": len(record.embedding),
                }
                for record in records
            ],
        },
    )
