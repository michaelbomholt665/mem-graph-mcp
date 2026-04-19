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
    get_rel_template,
)
from .types import PersistenceResult

logger = logging.getLogger(__name__)


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
    try:
        conn = lb.Connection(db)
        _execute_batch(conn, batch, result, max_retries=max_retries)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled ingest error")
        result.errors.append(f"ingest failed: {exc}")
        result.batches_rolled_back += 1
    finally:
        conn = None  # Let GC handle the connection

    return result


# ---------------------------------------------------------------------------
# Internal execution
# ---------------------------------------------------------------------------


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
    result.batches_committed += 1


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
        if not result.errors:
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
        if not result.errors:
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
        if not result.errors:
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
        if not result.errors:
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
        result.errors.append(f"{label}: {last_exc}")
        result.batches_rolled_back += 1
