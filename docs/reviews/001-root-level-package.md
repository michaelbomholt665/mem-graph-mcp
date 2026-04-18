# Code Review: `src/mem_graph` — Root-Level Package

**Reviewed:** 2026-04-14
**Scope:** `__init__.py`, `auth.py`, `config.py`, `db.py`, `embeddings.py`, `ids.py`, `logging.py`, `server.py`

---

## Summary

The root package is well-structured and clearly separated by concern. Key patterns (UUIDv7 IDs, instrumented DB connection, hybrid logging, model-tier abstraction) are sound. A few security and performance issues warrant attention, and one dead-code concern (`auth_api_middleware`) needs resolution.

---

## Critical Issues

| # | File | Line | Issue | Severity |
|---|------|------|-------|----------|
| 1 | `server.py` | ~155 | **Starlette REST routes bypass auth.** The `/dashboard/api/graph`, `/dashboard/api/node/{id}`, `/dashboard/api/search`, and `/file-tree/api/*` endpoints are Starlette `Route` objects not guarded by `StaticTokenVerifier`. When `MEM_GRAPH_API_KEYS` is set, the MCP layer is protected but the web API endpoints are publicly accessible, potentially leaking graph data and file-tree metadata. | 🔴 Critical |
| 2 | `db.py` | ~263 | **SQL injection risk — table/index names via f-string interpolation.** `db_update_embedding` constructs Cypher queries using `f"CALL DROP_VECTOR_INDEX('{table}', '{index_name}')"`. These values come from internal callers today, but they are not validated or allowlisted. Any path that passes user-influenced data to these parameters could be exploited for graph injection. | 🔴 Critical |

---

## Suggestions

| # | File | Line | Suggestion | Category |
|---|------|------|------------|----------|
| 1 | `embeddings.py` | ~205 | **LRU cache is O(n) per access.** `_cache_keys.remove(key)` is a linear scan. With `EMBED_CACHE_SIZE=512` it is tolerable, but under high load (many concurrent tool calls) this becomes a bottleneck. Replace `list` + `dict` with `collections.OrderedDict` for O(1) move-to-end semantics. | Performance |
| 2 | `embeddings.py` | ~120 | **`embeddings_documents` is sequential.** The loop `[await _cached_embed_async(t, "document") for t in texts]` processes each document one at a time. Replace with `asyncio.gather(*[_cached_embed_async(t, "document") for t in texts])` to parallelise uncached embeddings. | Performance |
| 3 | `auth.py` | ~65 | **`request.client` can be `None` in ASGI test environments.** `logger.warning("... from %s", request.client)` will log `None`, which is harmless but misleading. Use `request.client.host if request.client else "unknown"` for clarity. | Correctness |
| 4 | `db.py` | ~218 | **`db_close_engine` relies on GC for cleanup.** Setting refs to `None` without calling an explicit close/disconnect method is risky if `lb.Connection` holds file locks (e.g., WAL files). Call an explicit close API if the library exposes one. | Correctness |
| 5 | `db.py` | ~333 | **Repeated pattern `if isinstance(result, list): result = result[0]`** appears in `_init_schema_meta` and many resource handlers in `server.py`. If the list is empty this raises `IndexError`. Extract a helper `_unwrap_result(result)` with bounds checking. | Correctness |
| 6 | `server.py` | ~113 | **Dummy `OPENAI_API_KEY` masks misconfiguration.** Setting `os.environ.setdefault("OPENAI_API_KEY", "missing-key-set-in-env-file")` prevents import-time crashes but will produce confusing `401 Unauthorized` errors from any agent that actually fires against OpenAI. An explicit startup warning log would be safer than a silent fallback. | Maintainability |
| 7 | `auth.py` | whole file | **`auth_api_middleware` is dead code.** `server.py` exclusively uses `StaticTokenVerifier` (FastMCP 3.0 auth). The `auth_api_middleware` class and `auth_verify_key` function are never imported by the server. Remove or move to an archive module to avoid confusion about which auth layer is active. | Maintainability |
| 8 | `server.py` | ~295 | **Malformed Base64 in `Icon.src`.** The SVG data-URI string contains a literal newline inside the Base64 payload (visible around `ImhlaWdodD0i NDgiLz4...`). Browsers and MCP clients that parse the icon may silently ignore it or fail to render it. The Base64 string should be a single unbroken line. | Maintainability |
| 9 | `config.py` | ~135 | **`JINA_TOKEN` stored in module-level string.** Ensure this value is never passed to logging calls, exception messages, or responses. Consider wrapping in a `SecretStr` (Pydantic) so accidental serialisation is prevented. | Security |
| 10 | `server.py` | ~405 | **`tools_search` calls `mcp.list_tools()` on every invocation.** At scale with many namespaces active, this traversal is O(n tools) per search. Cache the tool list or build an in-process index at startup. | Performance |

---

## What Looks Good

- **`ids.py`** — Correct use of UUIDv7 (`uuid_utils`) for sortable, collision-resistant node IDs. Clean and minimal.
- **`db.py` `_InstrumentedConnection`** — Excellent OpenTelemetry integration: span per query, fingerprinting via SHA-256, result-count metrics.
- **`db.py` per-table `asyncio.Lock`** — The `_index_locks` dict-guarded DROP/SET/CREATE DDL sequence is a correct and safe pattern for Ladybug's constraint.
- **`config.py`** — Model-tier enum + `MODEL_TIER_MAP` is a clean single-source-of-truth for LLM routing. Using `os.getenv` with defaults makes it easy to override in CI.
- **`logging.py`** — Dual-format logging (JSON for production, console for dev) with OTel trace-context injection is production-grade.
- **`server.py` `StaticTokenVerifier`** — Correct FastMCP 3.0 auth pattern, scopes included, health endpoint exempted via Starlette-level routing.
- **`embeddings.py`** — Provider normalisation (`_normalise_model_name`), dimension validation on every result, and test override hook are all sound practices.

---

## Verdict

**Request Changes** — Two critical issues (unauthenticated REST API endpoints, Cypher f-string injection) must be addressed before production deployment. The remaining items are improvements that would increase robustness and performance.
