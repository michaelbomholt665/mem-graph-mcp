Good. Here's the plan — flat and functional, no architecture astronautics.

---

## Project structure

```
syntx-mcp/
├── src/
│   └── mem-graph/
│       ├── __init__.py
│       ├── server.py          # FastMCP app + lifespan
│       ├── db.py              # Ladybug connection + schema bootstrap
│       ├── embeddings.py      # Ollama embed helper
│       └── tools/
│           ├── __init__.py
│           ├── conversation.py
│           ├── memory.py
│           ├── projects.py
│           ├── tasks.py
│           ├── decisions.py
│           ├── notes.py
│           └── violations.py
├── schema/
│   └── agent_memory_schema.cypher
├── .env
└── pyproject.toml
```

---

## Lifespan + wiring (`server.py`)

```python
from contextlib import asynccontextmanager
from fastmcp import FastMCP
from .db import init_db, close_db
from .tools import conversation, memory, projects, tasks, decisions, notes, violations

@asynccontextmanager
async def lifespan(server: FastMCP):
    await init_db()
    yield
    await close_db()

mcp = FastMCP(
    "syntx-memory",
    instructions="Agent memory store for Syntx. Captures conversations, tasks, decisions, notes, violations and enables semantic recall across sessions.",
    lifespan=lifespan,
)

# Mount tool groups
mcp.include_module(conversation)
mcp.include_module(memory)
mcp.include_module(projects)
mcp.include_module(tasks)
mcp.include_module(decisions)
mcp.include_module(notes)
mcp.include_module(violations)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=9100)
```

---

## Tool inventory

These are the tools each module exposes. Signatures are the spec — implementation fills in the Ladybug Cypher calls.

### `conversation.py` — automatic capture

```
conversation_start(project_id, agent_name, model)     → conversation_id
conversation_append(conversation_id, role, content)   → message_id
conversation_end(conversation_id)                     → summary (auto-generated via Ollama)
conversation_get(conversation_id)                     → full message list
```

`conversation_append` is the key one — every agent turn calls this automatically. The agent just needs to call `conversation_start` at session open and `conversation_end` at close. Everything in between is captured via `conversation_append`.

### `memory.py` — distilled recall

```
memory_store(content, kind, scope, project_id?)       → memory_id
memory_recall(query, scope?, project_id?, limit=10)   → ranked memories  ← vector search
memory_search(query, limit=10)                        → cross-scope search
memory_expire(memory_id)                              → marks expired
memory_list(scope?, project_id?)                      → list without semantic ranking
```

`memory_recall` is the workhorse — takes a query string, embeds it via Ollama, runs `QUERY_VECTOR_INDEX` against the `Memory` table, returns top-k with scores.

### `projects.py`

```
project_create(name, description, repo_path?)        → project_id
project_get(project_id)                              → project node
project_list()                                       → all projects
project_search(query)                                → semantic search
```

### `tasks.py`

```
task_create(project_id, title, description, priority?, backend_id?)  → task_id
task_update(task_id, status?, phase?, priority?)                      → ok
task_get(task_id)                                                     → task node
task_search(query, project_id?)                                       → semantic search
task_link_decision(task_id, decision_id)                              → ok
task_link_violation(task_id, violation_id)                            → ok
task_block(task_id, blocked_by_task_id, reason)                       → ok
```

### `decisions.py`

```
decision_record(project_id, title, rationale, alternatives?, impact?) → decision_id
decision_supersede(old_id, new_id, reason)                            → ok
decision_get(decision_id)                                             → decision + lineage
decision_search(query, project_id?)                                   → semantic search
```

### `notes.py`

```
note_create(content, kind?, project_id?, tags?)      → note_id
note_search(query, kind?, project_id?)               → semantic search
note_list(project_id?, kind?)                        → list
```

### `violations.py`

```
violation_record(project_id, audit_id, rule, severity, file_path, description, backend_id?)  → violation_id
violation_resolve(violation_id)                                                               → ok
violation_recur(original_id, new_description)                                                → new_violation_id
violation_search(query, project_id?, status?)                                                → semantic search
violation_list(project_id?, status?)                                                         → list
```

---

## `.env`

```env
LADYBUG_DB_PATH=./data/syntx_memory.lbug
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_EMBED_DIM=768
MCP_HOST=127.0.0.1
MCP_PORT=9100
```

---

## Implementation order

1. `db.py` — connection singleton + run schema file on first boot
2. `embeddings.py` — single `embed(text: str) -> list[float]` function wrapping `ollama`
3. `conversation.py` — start/append/end, this is the auto-capture path
4. `memory.py` — store + recall with vector search
5. Everything else — projects, tasks, decisions, notes, violations in any order

The only real dependency chain is that conversation tools need embeddings, and memory recall needs embeddings. Everything else is straight Cypher writes and reads.

---

## One thing to decide before you start

The embedding dim in `.env` (`OLLAMA_EMBED_DIM=768` for `nomic-embed-text`) must match `FLOAT[N]` in the schema. Pick your model first, set the dim, then run the schema bootstrap. Changing it later means dropping and recreating all vector indexes plus re-embedding everything already stored.