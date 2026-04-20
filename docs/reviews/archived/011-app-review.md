# Code Review — `src/mem_graph/app/`

**Reviewer:** GitHub Copilot
**Resolved:** 2026-04-19
**Status:** ✅ COMPLETE — all issues fixed
**Package:** `src/mem_graph/app/`
**Files reviewed:** 41 Python files under `src/mem_graph/app/`, including the top-level FastMCP app wiring plus `parsers/`, `parsers/extractors/`, and `parsers/resolvers/`.

---

## Summary

This package is the FastMCP integration layer: HTTP routing, lifespan wiring, dashboard handlers, auth, public MCP tools/resources/prompts, and the tree-sitter parser pipeline. The overall separation is good, especially the split between app wiring and parser internals. The main concerns are around lifecycle hardening, silent parser degradation, and HTTP handlers that expose raw errors or fail on malformed query parameters.

---

## Issues

### 1. Several HTTP handlers return raw internal exception messages to clients — MEDIUM

**Location:** `web.py:41-62`, `web.py:247-255`, `web.py:280-302`, `web.py:337-339`

The health and dashboard endpoints embed `str(exc)` directly in JSON responses. That leaks internal database, network, and filesystem error details to any caller that can hit those routes.

Examples:

- `_health()` returns `{"db": "error: ...", "ollama": "error: ..."}`
- `_dashboard_node()` and `_dashboard_search()` return `{"error": str(exc)}`
- `_file_tree_data()` returns raw exception text on failure

**Suggested fix:** Log detailed exceptions server-side, but return a stable public error shape such as `"status": "degraded"` or `"error": "internal failure"`.

---

### 2. Multiple dashboard endpoints parse integers directly from query params and can 500 on bad input — MEDIUM

**Location:** `web.py:196`, `web.py:266-267`, `web.py:297`, `web.py:331`

Handlers such as `_dashboard_evals()`, `_dashboard_graph()`, `_dashboard_search()`, and `_file_tree_data()` call `int(request.query_params.get(...))` directly. A value like `?limit=abc` or `?depth=NaN` raises `ValueError`, which currently becomes a 500 in some paths and an opaque error in others.

**Suggested fix:** Centralize bounded integer parsing with validation and return 400 for malformed input.

---

### 3. Lifespan startup and shutdown are not wrapped in `try/finally` — MEDIUM

**Location:** `lifespan.py:35-107`

`build_lifespan()` starts the DB, summarizer worker, task queue, and OpenAPI providers before `yield`, then shuts them down afterward. Because there is no `try/finally` around the `yield`, cleanup depends on every step succeeding in order.

That leaves two failure modes:

1. If startup fails after a partial initialization, earlier resources may remain live.
2. If shutdown fails partway through, later cleanup steps are skipped.

This is exactly the kind of lifecycle edge case FastMCP lifespans are meant to make explicit.

**Suggested fix:** Wrap the `yield` and teardown in `try/finally`, and guard individual shutdown steps so one failure does not prevent the rest.

---

### 4. Parser query load failures silently degrade extraction — MEDIUM

**Location:** `parsers/loader.py:124-135`

`load_query_from_manifest()` returns `None` both when the query file is missing and when query compilation fails. It does so without logging why. That makes broken or stale tree-sitter query assets look the same as an intentionally absent query file.

In practice, this can quietly disable parser behavior instead of surfacing an actionable error during development or startup.

**Suggested fix:** Log or surface distinct warnings for file-read failure vs. query-compilation failure, even if the caller still chooses to continue.

---

### 5. `max_parse_ms` is enforced only after parsing completes — LOW

**Location:** `parsers/loader.py:214-233`, `parsers/safety.py:73-78`

The parse deadline is measured after `parser.parse(content)` returns. That means an expensive parse is allowed to run to completion before the limit is checked, so `max_parse_ms` is currently observational rather than preventative.

This is still useful for reporting, but it will not protect the server from a single pathological parse taking too long.

**Suggested fix:** Document the limit as post-parse telemetry, or move to a parsing strategy that can be interrupted or isolated with a timeout boundary.

---

### 6. `system_inspect` uses a nullable context with a type-ignore instead of normal DI semantics — LOW

**Location:** `tools.py:76-85`, `tools.py:131-135`

`system_inspect()` and its alias declare `ctx: Context = None  # type: ignore[assignment]` and then return an error dict when context is missing. That works, but it weakens the function signature and turns a wiring mistake into a normal-looking tool result.

**Suggested fix:** Use a normal injected `Context` parameter and let missing-context failures surface as programming errors instead of data results.

---

### 7. The loader cache comment says “oldest” but implements FIFO eviction, not true recency-based eviction — LOW

**Location:** `parsers/loader.py:67-75`, `parsers/loader.py:106-113`

The language and query caches evict `next(iter(cache))`, which removes the earliest inserted entry. Because cache hits do not refresh ordering, this is FIFO, not LRU. That is not wrong, but the implementation and mental model are easy to misread.

**Suggested fix:** Either rename the behavior in comments/docs or switch to an actual LRU container.

---

## Positive Observations

- The package cleanly separates FastMCP app wiring (`web`, `lifespan`, `tools`, `resources`, `prompts`) from parser mechanics.
- `web.py` uses `httpx.AsyncClient` correctly with an async context manager for the Ollama probe.
- The combined lifespan approach in `build_http_app()` explicitly avoids double-initializing the same FastMCP server across HTTP and SSE mounts.
- The parser pipeline has well-defined DTOs and layered responsibilities, which should make targeted fixes straightforward.

---

## Verdict

**Approve with comments.** I did not find a single blocker inside `src/mem_graph/app/`, but the lifecycle and error-handling issues are worth fixing before relying on these routes and parser flows in production-facing FastMCP deployments.
