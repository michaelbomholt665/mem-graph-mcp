"""
ingest.py — Single Ladybug DB execution boundary for parser ingest.

Owns:
- All Ladybug DB interactions for parser-written nodes and edges.
- Creating synchronous lb.Connection per ingest call.
- BEGIN TRANSACTION / COMMIT / ROLLBACK.
- Bounded batch sizing, retries, partial failure reporting.
- Structured PersistenceResult — never raises raw Ladybug exceptions.

Must not own:
- Parsing or AST traversal.
- Opening or closing the process-wide lb.Database.
- Embedding generation (accepts vectors as input only).
"""

from __future__ import annotations

import logging
from typing import Any

from .persist import (
    STALE_SYMBOL_CLEANUP,
    UPSERT_CODE_FILE,
    UPSERT_CODE_SYMBOL,
    CypherBatch,
    EdgeBatch,
    FileBatch,
    NodeBatch,
    get_rel_template,
)
from .types import PersistenceResult

logger = logging.getLogger(__name__)

_PARSER_FTS_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("CodeFile", "fts_codefile_path", ("path", "name", "summary")),
    ("CodeSymbol", "fts_symbol_name", ("name", "signature")),
)


# ---------------------------------------------------------------------------
# Ingest entry point
# ---------------------------------------------------------------------------


def ingest_batch(
    db: Any,  # lb.Database — passed in; never created here
    batch: CypherBatch,
    *,
    max_retries: int = 2,
) -> PersistenceResult:
    """
    Execute one CypherBatch against Ladybug.

    Creates a fresh synchronous lb.Connection per call (as required by
    Ladybug's single-writer model).

    Returns a structured PersistenceResult; never raises.
    """
    result = PersistenceResult()
    try:
        import real_ladybug as lb  # type: ignore[import-untyped]
    except ImportError as exc:
        result.errors.append(f"real_ladybug not available: {exc}")
        return result

    conn: Any = None
    suspended_fts_indexes: list[tuple[str, str, tuple[str, ...]]] = []
    try:
        conn = lb.Connection(db)
        suspended_fts_indexes = _suspend_parser_fts_indexes(conn)
        conn.execute("BEGIN TRANSACTION")
        try:
            _execute_batch(conn, batch, result, max_retries=max_retries)
            conn.execute("COMMIT")
            result.batches_committed += 1
        except Exception as exc:
            try:
                conn.execute("ROLLBACK")
            except Exception as rollback_exc:  # noqa: BLE001
                logger.warning("Batch rollback failed or was already aborted: %s", rollback_exc)
            result.batches_rolled_back += 1
            result.errors.append(f"Batch failed, rolled back: {exc}")
            logger.exception("Batch ingest error - rolled back")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled ingest error during connection/transaction setup")
        result.errors.append(f"ingest setup failed: {exc}")
        # Note: we don't increment batches_rolled_back here as we didn't even start the batch
    finally:
        if conn is not None and suspended_fts_indexes:
            _restore_parser_fts_indexes(conn, suspended_fts_indexes, result)
        conn = None  # Let GC handle the connection

    return result


def ingest_batch_data(
    db: Any,
    batch_data: dict[str, Any],
    *,
    max_retries: int = 2,
) -> PersistenceResult:
    """Reconstruct a CypherBatch from serialized data and ingest it."""
    return ingest_batch(db, batch_from_dict(batch_data), max_retries=max_retries)


# ---------------------------------------------------------------------------
# Internal execution
# ---------------------------------------------------------------------------


class IngestError(Exception):
    """Internal exception to trigger batch rollback."""


def batch_from_dict(batch_data: dict[str, Any]) -> CypherBatch:
    """Restore a CypherBatch from the JSON-safe staging representation."""
    edge_batches = {
        kind: EdgeBatch(
            kind=str(payload.get("kind") or kind),
            records=list(payload.get("records", [])),
        )
        for kind, payload in batch_data.get("edge_batches", {}).items()
    }
    return CypherBatch(
        file_batch=FileBatch(record=dict(batch_data.get("file_batch", {}).get("record", {}))),
        symbol_batch=NodeBatch(records=list(batch_data.get("symbol_batch", {}).get("records", []))),
        edge_batches=edge_batches,
        stale_cleanup_ids=list(batch_data.get("stale_cleanup_ids", [])),
        embedding_updates=list(batch_data.get("embedding_updates", [])),
    )


def _suspend_parser_fts_indexes(
    conn: Any,
) -> list[tuple[str, str, tuple[str, ...]]]:
    """
    Drop FTS indexes whose columns parser ingest mutates.

    Ladybug's FTS extension can crash while maintaining an index during batched
    MERGE/SET writes. Keep the write path stable by using the same
    drop-write-recreate pattern already required for vector-indexed updates.
    """
    existing = _existing_index_names(conn)
    suspended: list[tuple[str, str, tuple[str, ...]]] = []
    for table, index_name, props in _PARSER_FTS_INDEXES:
        if index_name not in existing:
            continue
        try:
            conn.execute(f"CALL DROP_FTS_INDEX('{table}', '{index_name}');")  # nosemgrep
            suspended.append((table, index_name, props))
        except Exception:
            logger.exception("Failed to suspend parser FTS index %s", index_name)
            raise
    return suspended


def _restore_parser_fts_indexes(
    conn: Any,
    indexes: list[tuple[str, str, tuple[str, ...]]],
    result: PersistenceResult,
) -> None:
    for table, index_name, props in indexes:
        props_str = ", ".join(f"'{prop}'" for prop in props)
        try:
            conn.execute(  # nosemgrep
                f"CALL CREATE_FTS_INDEX('{table}', '{index_name}', [{props_str}]);"
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to restore parser FTS index %s", index_name)
            result.errors.append(f"Failed to restore FTS index {index_name}: {exc}")


def _existing_index_names(conn: Any) -> set[str]:
    result = conn.execute("CALL SHOW_INDEXES() RETURN *;")
    rows = result.get_all() if hasattr(result, "get_all") else result
    return {str(row[1]) for row in rows}


def _execute_batch(
    conn: Any,
    batch: CypherBatch,
    result: PersistenceResult,
    *,
    max_retries: int,
) -> None:
    _ingest_file(conn, batch, result, max_retries)
    _ingest_symbols(conn, batch, result, max_retries)
    _ingest_edges(conn, batch, result, max_retries)
    _ingest_cleanup(conn, batch, result, max_retries)


def _ingest_file(
    conn: Any, batch: CypherBatch, result: PersistenceResult, max_retries: int
) -> None:
    if batch.file_batch.record:
        _execute_with_retry(
            conn,
            UPSERT_CODE_FILE,
            {"records": [batch.file_batch.record]},
            result,
            label="CodeFile",
            max_retries=max_retries,
        )
        result.files_written += 1


def _ingest_symbols(
    conn: Any, batch: CypherBatch, result: PersistenceResult, max_retries: int
) -> None:
    if batch.symbol_batch.records:
        _execute_with_retry(
            conn,
            UPSERT_CODE_SYMBOL,
            {"records": batch.symbol_batch.records},
            result,
            label="CodeSymbol",
            max_retries=max_retries,
        )
        result.symbols_written += len(batch.symbol_batch.records)


def _ingest_edges(
    conn: Any, batch: CypherBatch, result: PersistenceResult, max_retries: int
) -> None:
    _EDGE_ORDER = [
        "FILE_SYMBOL",
        "CONTAINS",
        "IMPORTS",
        "CALLS",
        "RESOLVES_TO",
        "EXTENDS",
        "IMPLEMENTS_SYMBOL",
        "HAS_TYPE",
        "RETURNS_TYPE",
        "READS_FROM",
        "PROJECTS",
        "FILTERS_ON",
        "JOINS_ON",
        "ALIASES",
    ]
    for kind in _EDGE_ORDER:
        eb = batch.edge_batches.get(kind)
        if not eb or not eb.records:
            continue
        template = get_rel_template(kind)
        if template is None:
            continue
        _execute_with_retry(
            conn,
            template,
            {"records": eb.records},
            result,
            label=kind,
            max_retries=max_retries,
        )
        result.relationships_written += len(eb.records)


def _ingest_cleanup(
    conn: Any, batch: CypherBatch, result: PersistenceResult, max_retries: int
) -> None:
    if batch.stale_cleanup_ids:
        _execute_with_retry(
            conn,
            STALE_SYMBOL_CLEANUP,
            {"stale_ids": batch.stale_cleanup_ids},
            result,
            label="stale_cleanup",
            max_retries=max_retries,
        )
        result.stale_symbols_cleaned += len(batch.stale_cleanup_ids)


def _execute_with_retry(
    conn: Any,
    query: str,
    params: dict[str, Any],
    result: PersistenceResult,
    label: str,
    max_retries: int,
) -> None:
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            conn.execute(query, params)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            result.retries += 1
            logger.warning(
                "Ingest retry %d/%d for %s: %s",
                attempt + 1,
                max_retries + 1,
                label,
                exc,
            )

    if last_exc is not None:
        raise IngestError(f"{label}: {last_exc}") from last_exc
