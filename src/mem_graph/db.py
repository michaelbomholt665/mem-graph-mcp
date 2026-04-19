#!/usr/bin/env python3
# src/mem_graph/db.py
"""
db.py — Ladybug connection singleton + schema bootstrap.

Initialization sequence (order matters):
  1. Open database file
  2. INSTALL + LOAD vector extension
  3. INSTALL + LOAD fts extension
  4. Run schema DDL (idempotent via IF NOT EXISTS), substituting embeddings_generate dim
  5. Create vector indexes guarded by SHOW_INDEXES() check
  6. Write/validate SchemaMeta node (raises RuntimeError on dim mismatch)
  7. Startup probe: verify Ollama is reachable

Call ``db_init_engine()`` once at server startup (FastMCP lifespan).
Call ``db_close_engine()`` at shutdown.
All tools should call ``db_get_connection()`` to obtain the active connection.

Thread-safety note
------------------
``db_update_embedding`` acquires a per-table ``asyncio.Lock`` before
the DROP_VECTOR_INDEX → SET → CREATE_VECTOR_INDEX sequence.  No tool
should call DROP_VECTOR_INDEX or CREATE_VECTOR_INDEX directly.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from pathlib import Path
from time import perf_counter
from typing import Any, cast

import ollama as _ollama
import real_ladybug as lb
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from .embeddings import CODE_EMBED_DIM, TEXT_EMBED_DIM
from .observability import logfire_debug, logfire_exception, record_graph_query

EMBED_DIM = TEXT_EMBED_DIM  # Legacy alias for tests

load_dotenv()

logger = logging.getLogger(__name__)
_QUERY_TRACER = trace.get_tracer("mem_graph.db")

# Regex pattern for validating SQL/Cypher identifiers
_IDENTIFIER_PATTERN = r"^[a-zA-Z_][\w]*$"
_IDENTIFIER_WITH_SPACE_PATTERN = r"^[a-zA-Z_][\w ]*$"
_DTYPE_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_\[\]]*$"

_db: lb.Database | None = None
_conn: lb.Connection | None = None
_conn_proxy: "_InstrumentedConnection | None" = None

SCHEMA_PATH = (
    Path(__file__).parent.parent.parent / "schema" / "agent_memory_schema.cypher"
)
DB_PATH = os.getenv("LADYBUG_DB_PATH", "./data/syntx_memory.lbug")
SCHEMA_VERSION = "1.2"

_KNOWN_EMBED_PROVIDERS = (
    "ollama",
    "openai",
    "google-gla",
    "google-vertex",
    "cohere",
    "voyageai",
    "bedrock",
    "sentence-transformers",
)

# Per-table locks that guard the DROP/SET/CREATE index cycle.
_index_locks: dict[str, asyncio.Lock] = {}


class _ObservedQueryResult:
    """Cache Ladybug query rows so result counts can be measured safely."""

    def __init__(self, result: Any) -> None:
        self._result = result
        self._rows: list[list[Any]] | None = None

    def get_all(self) -> list[list[Any]]:
        if self._rows is None:
            self._rows = cast(list[list[Any]], self._result.get_all())
        return self._rows

    def __iter__(self):
        return iter(self.get_all())

    def __len__(self) -> int:
        return len(self.get_all())

    def __getitem__(self, index: int) -> list[Any]:
        return self.get_all()[index]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._result, name)


class _InstrumentedConnection:
    """Proxy Ladybug connection calls so graph queries emit spans and metrics."""

    def __init__(self, connection: lb.Connection) -> None:
        self._connection = connection

    def execute(self, query: str, params: dict[str, Any] | None = None) -> Any:
        query_class = _classify_query(query)
        fingerprint = _query_fingerprint(query)
        start = perf_counter()
        with _QUERY_TRACER.start_as_current_span("graph.query") as span:
            span.set_attribute("db.system", "ladybug")
            span.set_attribute("logfire.msg", "graph.query")
            span.set_attribute("mem_graph.internal", True)
            span.set_attribute("graph.query.class", query_class)
            span.set_attribute("graph.query.fingerprint", fingerprint)
            span.set_attribute("graph.query.parameter_count", len(params or {}))

            try:
                raw_result = self._connection.execute(query, params or {})
                result, result_count = _instrument_result(raw_result)
            except Exception as exc:
                duration_ms = (perf_counter() - start) * 1000
                span.set_attribute("graph.query.duration_ms", duration_ms)
                span.set_attribute("graph.success", False)
                span.set_attribute("error.type", type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(exc)
                logfire_exception(
                    "Graph query failed",
                    query_class=query_class,
                    query_fingerprint=fingerprint,
                    parameter_count=len(params or {}),
                    duration_ms=duration_ms,
                    error_type=type(exc).__name__,
                )
                record_graph_query(query_class, duration_ms, status="error")
                raise

            duration_ms = (perf_counter() - start) * 1000
            span.set_attribute("graph.query.duration_ms", duration_ms)
            span.set_attribute("graph.success", True)
            span.set_status(Status(StatusCode.OK))
            if result_count is not None:
                span.set_attribute("graph.result.count", result_count)
            logfire_debug(
                "Graph query completed",
                query_class=query_class,
                query_fingerprint=fingerprint,
                parameter_count=len(params or {}),
                duration_ms=duration_ms,
                result_count=result_count if result_count is not None else -1,
            )
            record_graph_query(
                query_class,
                duration_ms,
                status="ok",
                result_count=result_count,
            )
            return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _normalize_query(query: str) -> str:
    return " ".join(query.split())


def _query_fingerprint(query: str) -> str:
    normalized = _normalize_query(query)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _classify_query(query: str) -> str:
    normalized = _normalize_query(query).upper()
    if normalized.startswith("CALL QUERY_VECTOR_INDEX"):
        return "vector-index-search"
    if normalized.startswith("CALL QUERY_FTS_INDEX"):
        return "fts-search"
    if normalized.startswith("CALL SHOW_INDEXES"):
        return "index-inspection"
    if "CREATE_VECTOR_INDEX" in normalized:
        return "vector-index-create"
    if "CREATE_FTS_INDEX" in normalized:
        return "fts-index-create"
    if "DROP_VECTOR_INDEX" in normalized:
        return "vector-index-drop"
    if normalized.startswith("MATCH"):
        return "match"
    if normalized.startswith("CREATE"):
        return "create"
    if normalized.startswith("MERGE"):
        return "merge"
    if normalized.startswith("SET") or " SET " in normalized:
        return "update"
    if normalized.startswith("DELETE") or normalized.startswith("DETACH DELETE"):
        return "delete"
    if normalized.startswith("INSTALL") or normalized.startswith("LOAD"):
        return "extension"
    return "query"


def _instrument_result(raw_result: Any) -> tuple[Any, int | None]:
    if isinstance(raw_result, list):
        return raw_result, len(raw_result)
    if hasattr(raw_result, "get_all"):
        observed_result = _ObservedQueryResult(raw_result)
        return observed_result, len(observed_result.get_all())
    return raw_result, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def db_get_connection() -> Any:
    """Return the active connection or raise if db_init_engine() was not called."""
    if _conn is None or _conn_proxy is None:
        raise RuntimeError("DB not initialized — call db_init_engine() first")
    return _conn_proxy


def db_init_engine() -> None:
    """Open the database, run bootstrap, probe Ollama.  Called from lifespan."""
    global _db, _conn, _conn_proxy

    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    _db = lb.Database(DB_PATH)
    _conn = lb.Connection(_db)
    _conn_proxy = _InstrumentedConnection(_conn)

    _bootstrap(_conn)
    _probe_ollama()


def db_close_engine() -> None:
    """Release the connection.  Ladybug closes on GC but be explicit."""
    global _db, _conn, _conn_proxy
    _conn = None
    _conn_proxy = None
    _db = None


async def db_update_embedding(
    table: str,
    node_id: str,
    vec: list[float],
    index_name: str,
) -> None:
    """
    Safely update an embedding column on a node that has a vector index.

    Ladybug/Kuzu cannot SET indexed columns directly — the index must be
    dropped first, the value updated, then the index recreated.  This
    function serialises that sequence per-table via an asyncio.Lock so
    concurrent callers don't corrupt the index.
    """
    # Validate identifiers to prevent injection
    if not re.match(_IDENTIFIER_PATTERN, table):
        raise ValueError(f"Invalid table name: {table}")
    if not re.match(_IDENTIFIER_PATTERN, index_name):
        raise ValueError(f"Invalid index name: {index_name}")

    lock = _index_locks.setdefault(table, asyncio.Lock())
    conn = db_get_connection()

    async with lock:
        conn.execute(f"CALL DROP_VECTOR_INDEX('{table}', '{index_name}');")  # nosemgrep
        conn.execute(  # nosemgrep
            f"MATCH (n:{table} {{id: $id}}) SET n.embedding = $vec",
            {"id": node_id, "vec": vec},
        )
        conn.execute(  # nosemgrep
            f"CALL CREATE_VECTOR_INDEX('{table}', '{index_name}', 'embedding', metric := 'cosine');"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _probe_ollama() -> None:
    """Fail loudly at startup if Ollama is not running, and pull models if missing."""
    from .config import CODE_EMBED_MODEL, TEXT_EMBED_MODEL

    models_to_check = [CODE_EMBED_MODEL, TEXT_EMBED_MODEL]

    try:
        models = _ollama.list()
        existing_models = [m.model for m in models.get("models", [])]

        for model in models_to_check:
            ollama_model = model.split(":")[-1] if ":" in model else model

            if (
                model not in existing_models
                and ollama_model not in existing_models
                and f"{ollama_model}:latest" not in existing_models
            ):
                logger.info(
                    "Ollama: Pulling required model '%s' (this may take a minute)...",
                    model,
                )
                _ollama.pull(model)
                logger.info("Ollama: Pulled '%s' successfully.", model)

    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Ollama is not reachable. Start Ollama before running syntx-mcp. "
            f"Original error: {exc}"
        ) from exc


def _bootstrap(conn: lb.Connection) -> None:
    # 1. Extensions — must happen before any DDL referencing vector types
    conn.execute("INSTALL vector; LOAD vector;")
    conn.execute("INSTALL fts;    LOAD fts;")
    # Optional extensions for parser pipeline — ignore if unavailable
    for ext in ("llm", "algo"):
        if not re.match(_IDENTIFIER_PATTERN, ext):
            continue
        try:
            conn.execute(f"INSTALL {ext}; LOAD {ext};")  # nosemgrep
        except Exception:
            pass

    # 2. Schema DDL — all IF NOT EXISTS so safe to re-run
    _run_schema(conn)

    # 3. Vector indexes — guarded manually (no IF NOT EXISTS equivalent)
    _ensure_vector_indexes(conn)

    # 4. FTS indexes — guarded by name check (same pattern as vector indexes)
    _ensure_fts_indexes(conn)

    # 5. Migrations — ensure old databases have new columns
    _migrate_schema(conn)

    # 6. SchemaMeta — write on first init, validate on subsequent startups
    _init_schema_meta(conn)


def _migrate_schema(conn: lb.Connection) -> None:
    """Safely add missing columns to existing tables."""
    migrations = [
        ("Violation", "last_seen_at", "TIMESTAMP"),
        ("Violation", "resolved_at", "TIMESTAMP"),
        ("EvalRun", "logfire_run_id", "STRING"),
        # CodeSymbol parser fields (Task 024)
        ("CodeSymbol", "qualified_name", "STRING"),
        ("CodeSymbol", "parent_id", "STRING"),
        ("CodeSymbol", "line_start", "INT64"),
        ("CodeSymbol", "line_end", "INT64"),
        ("CodeSymbol", "is_exported", "BOOLEAN"),
        ("CodeSymbol", "is_async", "BOOLEAN"),
        ("SchemaMeta", "text_embed_dim", "INT64"),
        ("SchemaMeta", "code_embed_dim", "INT64"),
    ]
    for table, column, dtype in migrations:
        # Validate identifiers to prevent injection
        if not re.match(_IDENTIFIER_PATTERN, table):
            raise ValueError(f"Invalid table name: {table}")
        if not re.match(_IDENTIFIER_PATTERN, column):
            raise ValueError(f"Invalid column name: {column}")
        if not re.match(_DTYPE_PATTERN, dtype):
            raise ValueError(f"Invalid data type: {dtype}")

        try:
            conn.execute(f"ALTER TABLE {table} ADD {column} {dtype};")  # nosemgrep
        except Exception:
            # Column likely already exists
            pass


def _init_schema_meta(conn: lb.Connection) -> None:
    """Write SchemaMeta on first run; validate dimensions on subsequent runs."""
    query_result = conn.execute(
        "MATCH (s:SchemaMeta {version: $v}) RETURN s.text_embed_dim, s.code_embed_dim",
        {"v": SCHEMA_VERSION},
    )
    if isinstance(query_result, list):
        query_result = query_result[0]

    result = cast(list[list[Any]], query_result.get_all())

    if not result:
        # First initialisation — write the meta node.
        conn.execute(
            """
            CREATE (s:SchemaMeta {
                version:        $v,
                text_embed_dim: $tdim,
                code_embed_dim: $cdim,
                initialized_at: current_timestamp()
            })
            """,
            {"v": SCHEMA_VERSION, "tdim": TEXT_EMBED_DIM, "cdim": CODE_EMBED_DIM},
        )
        return

    # Backwards compatibility check: old schemas might only have s.embed_dim
    # or the query returned NULL for new fields if they didn't exist.
    row = result[0]
    stored_tdim = int(row[0]) if row[0] is not None else None
    stored_cdim = int(row[1]) if row[1] is not None else None

    # If we find old SchemaMeta, we might need to handle it or just fail if it's too different.
    # For now, let's be strict if they are present.
    if stored_tdim is not None and stored_tdim != TEXT_EMBED_DIM:
        raise RuntimeError(
            f"Text embedding dimension mismatch: schema has {stored_tdim} but config has {TEXT_EMBED_DIM}."
        )
    if stored_cdim is not None and stored_cdim != CODE_EMBED_DIM:
        raise RuntimeError(
            f"Code embedding dimension mismatch: schema has {stored_cdim} but config has {CODE_EMBED_DIM}."
        )


def _clean_stmt(stmt: str) -> str:
    content_lines = []
    for ln in stmt.splitlines():
        stripped = ln.strip()
        if stripped.startswith("//"):
            continue
        dash_pos = ln.find(" --")
        if dash_pos != -1:
            ln = ln[:dash_pos]
        content_lines.append(ln)
    return "\n".join(content_lines).strip()


def _should_run_stmt(clean: str) -> bool:
    if not clean:
        return False
    upper = clean.upper()
    if upper.startswith("INSTALL") or upper.startswith("LOAD"):
        return False
    if upper.startswith("CALL CREATE_VECTOR_INDEX") or upper.startswith(
        "CALL DROP_VECTOR_INDEX"
    ):
        return False
    if not (
        upper.startswith("CREATE")
        or upper.startswith("DROP")
        or upper.startswith("ALTER")
    ):
        return False
    return True


def _run_schema(conn: lb.Connection) -> None:
    raw = SCHEMA_PATH.read_text()
    # Support two-tier embeddings via explicit placeholders
    raw = raw.replace("FLOAT[TEXT_DIM]", f"FLOAT[{TEXT_EMBED_DIM}]")
    raw = raw.replace("FLOAT[CODE_DIM]", f"FLOAT[{CODE_EMBED_DIM}]")
    # Fallback: replace any remaining FLOAT[d+] with TEXT_EMBED_DIM
    raw = re.sub(r"FLOAT\[\d+\]", f"FLOAT[{TEXT_EMBED_DIM}]", raw)

    for stmt in raw.split(";"):
        clean = _clean_stmt(stmt)
        if _should_run_stmt(clean):
            conn.execute(clean)  # nosemgrep


def _ensure_vector_indexes(conn: lb.Connection) -> None:
    # Fetch existing index names — index name is column[1]
    result = cast(list[list[str]], conn.execute("CALL SHOW_INDEXES() RETURN *;"))
    existing = {row[1] for row in result}

    indexes = [
        ("Project", "idx_project_emb", "embedding"),
        ("Backend", "idx_backend_emb", "embedding"),
        ("Task", "idx_task_emb", "embedding"),
        ("Decision", "idx_decision_emb", "embedding"),
        ("Note", "idx_note_emb", "embedding"),
        ("Violation", "idx_violation_emb", "embedding"),
        ("Conversation", "idx_conv_emb", "embedding"),
        ("Message", "idx_message_emb", "embedding"),
        ("Memory", "idx_memory_emb", "embedding"),
        ("CodeSymbol", "idx_symbol_emb", "embedding"),
        ("CodeFile", "idx_codefile_emb", "embedding"),
        ("JinaIssue", "idx_jina_issue_emb", "embedding"),
    ]

    for table, index_name, prop in indexes:
        if index_name in existing:
            continue
        # Validate identifiers
        if not (
            re.match(_IDENTIFIER_WITH_SPACE_PATTERN, table)
            and re.match(_IDENTIFIER_PATTERN, index_name)
            and re.match(_IDENTIFIER_PATTERN, prop)
        ):
            continue
        conn.execute(f"""
            CALL CREATE_VECTOR_INDEX(
                '{table}',
                '{index_name}',
                '{prop}',
                metric := 'cosine'
            );
        """)  # nosemgrep


def _ensure_fts_indexes(conn: lb.Connection) -> None:
    # Fetch existing index names — same SHOW_INDEXES() call used for vectors.
    result = cast(list[list[str]], conn.execute("CALL SHOW_INDEXES() RETURN *;"))
    existing = {row[1] for row in result}

    fts_indexes = [
        ("Memory", "fts_memory_content", ["content"]),
        ("Note", "fts_note_body", ["body", "title"]),
        ("Task", "fts_task_desc", ["description", "title"]),
        ("Decision", "fts_decision_rat", ["rationale", "title"]),
        ("Violation", "fts_violation_desc", ["description"]),
        ("CodeSymbol", "fts_symbol_name", ["name", "signature"]),
        ("CodeFile", "fts_codefile_path", ["path", "name", "summary"]),
        ("JinaIssue", "fts_jina_issue_text", ["issue_key", "title", "description"]),
    ]

    for table, index_name, props in fts_indexes:
        if index_name in existing:
            continue
        # Validate identifiers
        if not re.match(_IDENTIFIER_WITH_SPACE_PATTERN, table):
            continue
        if not re.match(_IDENTIFIER_PATTERN, index_name):
            continue
        if not all(re.match(_IDENTIFIER_PATTERN, p) for p in props):
            continue
        props_str = ", ".join(f"'{p}'" for p in props)
        conn.execute(  # nosemgrep
            f"CALL CREATE_FTS_INDEX('{table}', '{index_name}', [{props_str}]);"
        )
