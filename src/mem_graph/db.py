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
import logging
import os
from pathlib import Path
from typing import cast, Any

import ollama as _ollama
import real_ladybug as lb
from dotenv import load_dotenv

from .embeddings import EMBED_DIM
load_dotenv()

logger = logging.getLogger(__name__)

_db: lb.Database | None = None
_conn: lb.Connection | None = None

SCHEMA_PATH = (
    Path(__file__).parent.parent.parent / "schema" / "agent_memory_schema.cypher"
)
DB_PATH = os.getenv("LADYBUG_DB_PATH", "./data/syntx_memory.lbug")
SCHEMA_VERSION = "1.0"

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

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def db_get_connection() -> lb.Connection:
    """Return the active connection or raise if db_init_engine() was not called."""
    if _conn is None:
        raise RuntimeError("DB not initialized — call db_init_engine() first")
    return _conn


def db_init_engine() -> None:
    """Open the database, run bootstrap, probe Ollama.  Called from lifespan."""
    global _db, _conn

    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    _db = lb.Database(DB_PATH)
    _conn = lb.Connection(_db)

    _bootstrap(_conn)
    _probe_ollama()


def db_close_engine() -> None:
    """Release the connection.  Ladybug closes on GC but be explicit."""
    global _db, _conn
    _conn = None
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
    lock = _index_locks.setdefault(table, asyncio.Lock())
    conn = db_get_connection()

    async with lock:
        conn.execute(f"CALL DROP_VECTOR_INDEX('{table}', '{index_name}');")
        conn.execute(
            f"MATCH (n:{table} {{id: $id}}) SET n.embedding = $vec",
            {"id": node_id, "vec": vec},
        )
        conn.execute(
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

    # 2. Schema DDL — all IF NOT EXISTS so safe to re-run
    _run_schema(conn)

    # 3. Vector indexes — guarded manually (no IF NOT EXISTS equivalent)
    _ensure_vector_indexes(conn)

    # 4. FTS indexes — guarded by name check (same pattern as vector indexes)
    _ensure_fts_indexes(conn)

    # 5. SchemaMeta — write on first init, validate on subsequent startups
    _init_schema_meta(conn)


def _init_schema_meta(conn: lb.Connection) -> None:
    """Write SchemaMeta on first run; validate embed_dim on subsequent runs."""
    query_result = conn.execute(
        "MATCH (s:SchemaMeta {version: $v}) RETURN s.embed_dim",
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
                embed_dim:      $dim,
                initialized_at: current_timestamp()
            })
            """,
            {"v": SCHEMA_VERSION, "dim": EMBED_DIM},
        )
        return

    stored_dim = int(cast(int, result[0][0]))
    if stored_dim != EMBED_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch: schema was initialised with dim={stored_dim} "
            f"but OLLAMA_EMBED_DIM is currently {EMBED_DIM}. "
            "Either reset the database or set OLLAMA_EMBED_DIM to match the stored value."
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
    if upper.startswith("CALL CREATE_VECTOR_INDEX") or upper.startswith("CALL DROP_VECTOR_INDEX"):
        return False
    if not (upper.startswith("CREATE") or upper.startswith("DROP") or upper.startswith("ALTER")):
        return False
    return True

def _run_schema(conn: lb.Connection) -> None:
    raw = SCHEMA_PATH.read_text()
    raw = raw.replace("FLOAT[1536]", f"FLOAT[{EMBED_DIM}]")

    for stmt in raw.split(";"):
        clean = _clean_stmt(stmt)
        if _should_run_stmt(clean):
            conn.execute(clean)


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
    ]

    for table, index_name, prop in indexes:
        if index_name in existing:
            continue
        conn.execute(f"""
            CALL CREATE_VECTOR_INDEX(
                '{table}',
                '{index_name}',
                '{prop}',
                metric := 'cosine'
            );
        """)


def _ensure_fts_indexes(conn: lb.Connection) -> None:
    # Fetch existing index names — same SHOW_INDEXES() call used for vectors.
    result = cast(list[list[str]], conn.execute("CALL SHOW_INDEXES() RETURN *;"))
    existing = {row[1] for row in result}

    fts_indexes = [
        ("Memory",     "fts_memory_content", ["content"]),
        ("Note",       "fts_note_body",      ["body", "title"]),
        ("Task",       "fts_task_desc",      ["description", "title"]),
        ("Decision",   "fts_decision_rat",   ["rationale", "title"]),
        ("Violation",  "fts_violation_desc", ["description"]),
        ("CodeSymbol", "fts_symbol_name",    ["name", "signature"]),
    ]

    for table, index_name, props in fts_indexes:
        if index_name in existing:
            continue
        props_str = ", ".join(f"'{p}'" for p in props)
        conn.execute(
            f"CALL CREATE_FTS_INDEX('{table}', '{index_name}', [{props_str}]);"
        )
