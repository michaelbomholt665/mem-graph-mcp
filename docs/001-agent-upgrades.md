---
title: "001 — Agent Upgrades: GPT-5 Mini, Orchestrator, Embeddings"
date: 2026-04-13
updated: 2026-04-13
---

# Agent Upgrades & Embeddings Migration

## Status

| Track | Status | Files |
|---|---|---|
| A — Central config + GPT-5 mini defaults | **Ready to integrate** | `config.py` (new), all agents |
| B — Orchestrator agent | **Ready to integrate** | `orchestrator_agent.py` (new) |
| C — Embeddings migration | **Ready to integrate** | `embeddings.py` (rewrite) |

---

## Track A — Central config + agent defaults

### What was built

`src/mem_graph/config.py` — new file, single source of truth:

```python
AGENT_MODEL = os.getenv("MEM_GRAPH_AGENT_MODEL", "openai:gpt-5-mini")
DEFER_AGENT_MODEL_CHECK = True
```

### Integration steps

1. Drop `config.py` into `src/mem_graph/`.

2. In each agent file replace the local constant and Agent instantiation:

```python
# Before (in each agent file)
_AGENT_MODEL = os.getenv("MEM_GRAPH_AGENT_MODEL", "openai:gpt-4o")
audit_agent = Agent(_AGENT_MODEL, ...)

# After
from ..config import AGENT_MODEL, DEFER_AGENT_MODEL_CHECK
audit_agent = Agent(AGENT_MODEL, ..., defer_model_check=DEFER_AGENT_MODEL_CHECK)
```

Files to update:
- `src/mem_graph/agents/audit_agent.py`
- `src/mem_graph/agents/decision_agent.py`
- `src/mem_graph/agents/map_agent.py`
- `src/mem_graph/agents/task_agent.py`
- `src/mem_graph/agents/triage_agent.py`
- `src/mem_graph/agents/diagram_agent.py`
- `src/mem_graph/agents/orchestrator_agent.py` (already uses config)

3. Confirm `gpt-5-mini` model string with your provider. The canonical identifier
   may be `openai:gpt-5-mini` or differ — adjust `config.py` default if needed.

### Non-code rollout

Set in environment or `.env` without touching code:

```bash
MEM_GRAPH_AGENT_MODEL=openai:gpt-5-mini
```

---

## Track B — Orchestrator agent

### What was built

`src/mem_graph/agents/orchestrator_agent.py` — new file.

Key design decisions vs original plan:

**Files are pre-read before sub-agents run.** The orchestrator reads each
batch concurrently with `anyio.create_task_group`, then injects the content
into sub-agent deps via an `extra_file_context` field. Sub-agents receive
file content without making individual `read_file` tool calls — this is the
batched write-before-moving-on pattern that prevents lost-in-the-middle
context staleness.

**`process_batch` is atomic.** Read + invoke + record happens in one tool call.
The orchestrator agent cannot advance to the next batch without completing
`process_batch` on the current one — enforced by tool design, not prompt.

**Aggregation is incremental.** `_merge_into_aggregate` runs after every batch
so partial results survive sub-agent failures. Failed batches are flagged in
`batch_results` but do not abort the run.

**Three sub-agents supported: `audit`, `map`, `decision`.** Routed via
`OrchestratorDependencies.subagent_name`. Adding a new sub-agent requires
a new `_run_X_batch` function and a dispatch case in `_dispatch`.

### Integration steps

1. Drop `orchestrator_agent.py` into `src/mem_graph/agents/`.

2. Add `extra_file_context: str = ""` field to `AuditDependencies`,
   `MapDependencies`, and `DecisionDependencies` in their respective agent files.
   The orchestrator injects pre-read file content here.

3. Update the system prompts of audit, map, and decision agents to check for
   `extra_file_context` and skip `read_file` calls when it is populated:

```python
@audit_agent.system_prompt
async def build_system_prompt(ctx: RunContext[AuditDependencies]) -> str:
    file_section = (
        f"## Pre-loaded Files\n{ctx.deps.extra_file_context}\n\n"
        "All files above are pre-loaded. Do NOT call read_file."
        if ctx.deps.extra_file_context
        else ""
    )
    return f"""...{file_section}..."""
```

4. Expose via MCP tool in `src/mem_graph/tools/orchestrator.py` (new, follows
   the same pattern as `tools/audit.py`).

### Wiring extra_context for decision agent

The decision agent needs `decisions` injected. Pass them via
`OrchestratorDependencies.extra_context`:

```python
deps = OrchestratorDependencies(
    package_path="/path/to/pkg",
    project_id="proj-123",
    subagent_name="decision",
    extra_context={"decisions": [...]}  # serialised Decision nodes from graph
)
```

### Progress persistence

Current implementation holds state in-memory on `RunContext`.
For resume-after-failure, wire `persist_progress` / `load_progress` to the
graph or a temp file — stubbed in the design, not yet implemented.
Add when needed.

---

## Track C — Embeddings migration

### What changed vs original

The plan proposed `pydantic_ai.EmbeddingsModel` — this API does not exist
in pydantic-ai 0.0.34. The rewrite keeps Ollama as the backend (matching
your existing stack) but adds the infrastructure the plan called for:

- LRU-style cache keyed on `(text, model)` — 512 entry default, configurable
  via `MEM_GRAPH_EMBED_CACHE_SIZE`.
- `_embed_override` hook for test shims — set in `conftest.py`, no patching
  required.
- `embed_sync()` for any callers that cannot be async.
- `clear_cache()` for test teardown and post-model-change cleanup.
- Env var `MEM_GRAPH_EMBED_MODEL` is the new primary — falls back to
  `OLLAMA_EMBED_MODEL` for backwards compatibility.

When pydantic-ai ships native `EmbeddingsModel`, swap `_embed_sync_raw` and
the model init — everything above it stays the same.

### Integration steps

1. Replace `src/mem_graph/embeddings.py` with the new version.

2. No call site changes needed — `embed(text)` signature is identical.

3. Add to `tests/conftest.py`:

```python
import mem_graph.embeddings as emb

@pytest.fixture(autouse=True)
def deterministic_embeddings():
    emb._embed_override = lambda text: [0.0] * emb.EMBED_DIM
    yield
    emb._embed_override = None
    emb.clear_cache()
```

4. Update `.env` if switching embed model:

```bash
MEM_GRAPH_EMBED_MODEL=nomic-embed-text   # Ollama — keep existing behaviour
# or
MEM_GRAPH_EMBED_MODEL=openai:text-embedding-3-small  # when pydantic-ai native lands
```

5. `db.py` already reads `EMBED_DIM` from `embeddings.py` — no change needed there.

---

## New environment variables

| Variable | Default | Description |
|---|---|---|
| `MEM_GRAPH_AGENT_MODEL` | `openai:gpt-5-mini` | Model for all agents |
| `MEM_GRAPH_EMBED_MODEL` | `nomic-embed-text` | Embedding model (Ollama) |
| `MEM_GRAPH_EMBED_CACHE_SIZE` | `512` | LRU cache size for embeddings |

`OLLAMA_EMBED_MODEL` and `OLLAMA_EMBED_DIM` remain supported as fallbacks.

---

## Open items

- Confirm `openai:gpt-5-mini` model string with your provider before deploying Track A.
- Implement progress persistence for orchestrator (Track B) when resume is needed.
- Swap `_embed_sync_raw` to pydantic-ai native when `EmbeddingsModel` ships.
- Add `triage` and `task` sub-agents to orchestrator dispatch when those agents
  are validated — they don't read files so the batching pattern doesn't apply directly,
  but the coordination pattern does.