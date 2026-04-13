Yeah, Ladybug's Go client is thin and the Python client has some rough edges around bootstrapping. Let me think through what actually needs to happen.

---

## The real initialization problem

Ladybug is embedded — there's no server to connect to, no migration runner, no `CREATE TABLE IF NOT EXISTS` safety net by default (well, it exists but you need to be careful with the vector extension loading order). The sequence matters:

```
1. Open database file
2. INSTALL + LOAD vector extension
3. INSTALL + LOAD fts extension  
4. Run schema DDL (idempotent via IF NOT EXISTS)
5. Create vector indexes (will error if table is empty AND index exists — Ladybug quirk)
6. Connection ready
```

The vector index creation is the landmine. `CALL CREATE_VECTOR_INDEX(...)` throws if the index already exists — there's no `IF NOT EXISTS` equivalent for indexes. You have to check `SHOW_INDEXES()` first and skip creation if it's already there.

---

## `db.py`

```python
# src/mem-graph/db.py
import os
from pathlib import Path
import real_ladybug as lb
from dotenv import load_dotenv

load_dotenv()

_db: lb.Database | None = None
_conn: lb.Connection | None = None

SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "agent_memory_schema.cypher"
DB_PATH = os.getenv("LADYBUG_DB_PATH", "./data/syntx_memory.lbug")
EMBED_DIM = int(os.getenv("OLLAMA_EMBED_DIM", "768"))


def get_conn() -> lb.Connection:
    if _conn is None:
        raise RuntimeError("DB not initialized — call init_db() first")
    return _conn


async def init_db() -> None:
    global _db, _conn

    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    _db = lb.Database(DB_PATH)
    _conn = lb.Connection(_db)

    _bootstrap(_conn)


def close_db() -> None:
    global _db, _conn
    _conn = None
    _db = None  # Ladybug closes on GC, but be explicit


def _bootstrap(conn: lb.Connection) -> None:
    # 1. Extensions first — must happen before any DDL that references vector types
    conn.execute("INSTALL vector; LOAD vector;")
    conn.execute("INSTALL fts;    LOAD fts;")

    # 2. Schema DDL — all IF NOT EXISTS so safe to re-run
    _run_schema(conn)

    # 3. Vector indexes — guarded manually
    _ensure_vector_indexes(conn)


def _run_schema(conn: lb.Connection) -> None:
    raw = SCHEMA_PATH.read_text()

    # Strip the INSTALL/LOAD lines — already done above
    # Strip the CALL CREATE_VECTOR_INDEX lines — handled separately
    # Strip comment blocks and example queries
    statements = []
    for stmt in raw.split(";"):
        s = stmt.strip()
        if not s:
            continue
        # Skip lines we handle separately or that are comments-only
        upper = s.upper()
        if upper.startswith("INSTALL") or upper.startswith("LOAD"):
            continue
        if upper.startswith("CALL CREATE_VECTOR_INDEX"):
            continue
        if upper.startswith("CALL DROP_VECTOR_INDEX"):
            continue
        if upper.startswith("//"):
            continue
        statements.append(s)

    for stmt in statements:
        # Strip inline comments
        lines = [l for l in stmt.splitlines() if not l.strip().startswith("//")]
        clean = "\n".join(lines).strip()
        if clean:
            conn.execute(clean)


def _ensure_vector_indexes(conn: lb.Connection) -> None:
    # Get existing indexes
    result = conn.execute("CALL SHOW_INDEXES() RETURN *;")
    existing = {row[1] for row in result.get_all()}  # index name is col[1]

    indexes = [
        ("Project",      "idx_project_emb",    "embedding"),
        ("Backend",      "idx_backend_emb",     "embedding"),
        ("Task",         "idx_task_emb",        "embedding"),
        ("Decision",     "idx_decision_emb",    "embedding"),
        ("Note",         "idx_note_emb",        "embedding"),
        ("Violation",    "idx_violation_emb",   "embedding"),
        ("Conversation", "idx_conv_emb",        "embedding"),
        ("Message",      "idx_message_emb",     "embedding"),
        ("Memory",       "idx_memory_emb",      "embedding"),
        ("CodeSymbol",   "idx_symbol_emb",      "embedding"),
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
```

---

## `embeddings.py`

The other thing that needs care — Ollama's embed call is synchronous in the SDK but your FastMCP server is async. Wrap it properly or you'll block the event loop.

```python
# src/mem-graph/embeddings.py
import os
import asyncio
from functools import partial
import ollama
from dotenv import load_dotenv

load_dotenv()

_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
_DIM   = int(os.getenv("OLLAMA_EMBED_DIM", "768"))


def _embed_sync(text: str) -> list[float]:
    """Blocking call — run in thread pool, don't call directly from async."""
    response = ollama.embed(model=_MODEL, input=text)
    vec = response.embeddings[0]
    if len(vec) != _DIM:
        raise ValueError(
            f"Embedding dim mismatch: got {len(vec)}, expected {_DIM}. "
            f"Check OLLAMA_EMBED_MODEL and OLLAMA_EMBED_DIM in .env"
        )
    return vec


async def embed(text: str) -> list[float]:
    """Async-safe embed — offloads blocking Ollama call to thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_embed_sync, text))


def embed_dim() -> int:
    return _DIM
```

---

## The schema file needs one fix

The `FLOAT[1536]` hardcoded in the schema won't match `nomic-embed-text` (768 dims). You have two options — either patch the schema at bootstrap time using the env var, or just edit the schema file to use `FLOAT[768]` now that you've picked your model.

Patching at bootstrap is cleaner for a tool you might hand to buyers:

```python
def _run_schema(conn: lb.Connection) -> None:
    raw = SCHEMA_PATH.read_text()
    # Substitute embedding dimension from env
    raw = raw.replace("FLOAT[1536]", f"FLOAT[{EMBED_DIM}]")
    ...
```

Add that one line before the statement splitting loop and the schema becomes model-agnostic.

---

## What can still bite you

**First run on an existing `.lbug` file** — if the db file exists but the schema failed halfway through a previous run, you might have partial tables. There's no rollback across DDL in Ladybug. The `IF NOT EXISTS` guards protect you mostly, but a genuinely corrupt bootstrap means deleting the `.lbug` file and starting over. For dev this is fine. For a buyer environment you'll want a schema version node (`Memory` with `kind='schema_version'`) so you can detect and refuse to run against a mismatched schema rather than silently corrupting it.

**Vector index on empty table** — Ladybug creates the HNSW index fine on an empty table, but querying it returns nothing rather than erroring. That's expected behavior, not a bug.

**Ollama not running** — `embed()` will throw at the first tool call that needs it. Worth adding a startup probe in `init_db()` that calls `ollama.list()` and fails loud if the service is unreachable, rather than getting a cryptic error later mid-conversation.