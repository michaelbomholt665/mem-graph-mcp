# Services README

## Current Structure

| File | Lines | Role | Key Dependencies |
|------|-------|------|------------------|
| `embed_client.py` | 101 | Generic retry-with-backoff base class | None |
| `jina_common.py` | 230 | Shared Jina models, constants, and utilities | pydantic |
| `code_embed_service.py` | 237 | Code file indexing and CodeFile persistence | jina_common, db, app/parsers |
| `text_embed_service.py` | 427 | Jina issue fetching, persistence, semantic matching | embed_client, jina_common, code_embed_service, db |
| `jina_embedder.py` | 233 | Facade coordinating Jina ingestion and matching | embed_client, code_embed_service, text_embed_service, jina_common |
| `graph_context_service.py` | 249 | High-level read-only graph queries | db, models/work |
| `graph_writer_service.py` | 156 | Shared node/relationship write operations | db, ids |
| `fingerprint.py` | 98 | Deterministic deduplication for audit findings | models/audit |
| `violation_writer.py` | 236 | Audit findings → Violation nodes | fingerprint, graph_writer_service, db, models/audit |
| `report_writer.py` | 308 | AuditReport → markdown renderer | models/audit |
| `memory.py` | 161 | Instrumented memory persistence | db, embeddings, observability |
| `sandbox_sessions.py` | 22 | Thin accessor for process-wide sandbox manager | sandbox/ |
| `search.py` | 25 | RRF fusion for hybrid vector + FTS search | None |
| `summarizer.py` | 205 | Background conversation summarization worker | embed_client, db, embeddings, observability |
| `task_queue.py` | 299 | Bounded in-memory task queue | models/task, observability |

## Dependency Analysis

### Jina/Embedding Pipeline (4 files, deeply coupled)
`jina_common` ← `code_embed_service` ← `text_embed_service` ← `jina_embedder`
- `jina_embedder` is the public facade, delegating to `text_embed_service` and `code_embed_service`
- `jina_common` provides shared models (`JinaIssue`, `CodeMatch`, `IndexedCodeFile`) and utilities
- `embed_client` is used by `text_embed_service`, `jina_embedder`, and `summarizer` — it is **not** Jina-specific

### Audit Pipeline (3 files, linear chain)
`fingerprint` → `violation_writer` → (used by audit tools)
`report_writer` → (used by audit tools, independent of violation_writer at import time)
- `fingerprint.py` is only imported by `violation_writer.py`
- `report_writer.py` and `violation_writer.py` both depend on `models/audit` but not on each other

### Graph Operations (2 files, loosely related)
`graph_context_service` — read-only queries
`graph_writer_service` — write operations used by `violation_writer`
- Both depend on `db` but have no dependency on each other

### Standalone Services
- `memory.py` — self-contained memory persistence
- `sandbox_sessions.py` — bridge to `sandbox/` package (22 lines)
- `search.py` — pure utility function (25 lines)
- `summarizer.py` — background worker, depends on `embed_client`
- `task_queue.py` — concurrency infrastructure

## Refactor Suggestion

### Primary: Extract Jina pipeline into sub-package
Move the 4 tightly-coupled Jina files into `services/jina/`, which matches their actual dependency boundary:

- **jina/**: `jina_common.py`, `code_embed_service.py`, `text_embed_service.py`, `jina_embedder.py`

Keep `embed_client.py` in `services/` root — it is a generic retry base used by both the Jina pipeline and `summarizer.py`, so it should not be inside `jina/`.

### Secondary: Extract audit pipeline into sub-package
- **audit/**: `fingerprint.py`, `violation_writer.py`, `report_writer.py`

These three form a complete audit-findings-to-graph pipeline with no external service dependencies beyond `graph_writer_service` and `models/audit`. Grouping them makes the audit write path easier to find and test in isolation.

### Optional: Extract graph operations
- **graph/**: `graph_context_service.py`, `graph_writer_service.py`

Both are thin wrappers over raw Cypher. Grouping them clarifies that `services/` contains business logic above the raw DB layer.

### Files staying in root
`__init__.py`, `embed_client.py`, `memory.py`, `sandbox_sessions.py`, `search.py`, `summarizer.py`, `task_queue.py`

These are either too small to move (`search.py`, `sandbox_sessions.py`), cross-cutting (`embed_client.py`), or standalone services with no natural sub-package.

### Not recommended
- Moving `embed_client.py` into `jina/` — it would create a circular or awkward dependency since `summarizer.py` also uses it
- Creating a `writers/` sub-package for just `report_writer.py` and `violation_writer.py` — they serve different concerns (rendering vs graph persistence) and the audit/ grouping captures their relationship better
