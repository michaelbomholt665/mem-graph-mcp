# Code Review: `src/mem_graph/services/`

**Reviewed:** 2026-04-14
**Scope:** `fingerprint.py`, `jina_embedder.py`, `memory.py`, `report_writer.py`, `search.py`, `summarizer.py`, `task_queue.py`, `violation_writer.py`

---

## Summary

The services layer is the backbone of persistence, search, and background work. The task queue, violation writer, and summariser are solid. (Note: Summarizer shutdown timeout behavior is now covered in 017-services-review.md). Two security issues need remediation: a JQL injection in `jina_embedder.py` and a leaked Jina credential in error-log paths.

---

## Critical Issues

| # | File | Line | Issue | Severity |
|---|------|------|-------|----------|
| 1 | `jina_embedder.py` | ~370 | **JQL injection via `issue_key`.** `fetch_issue` interpolates a caller-supplied string directly into a JQL statement: `jql=f"key = {issue_key.strip().upper()}"`. An input like `"MEM-1 OR issueType = Bug"` or `"MEM-1 ORDER BY votes DESC"` mutates the query. Although `.upper()` is applied, it does not prevent structural JQL manipulation. Fix: validate that `issue_key` matches the pattern `^[A-Z][A-Z0-9]+-\d+$` before interpolation, or use quoting (`key = "{key}"`). | 🔴 Critical |

---

## Suggestions

| # | File | Line | Suggestion | Category |
|---|------|------|------------|----------|
| 1 | `jina_embedder.py` | ~350 | **Jina token visible in exception messages.** When `response.raise_for_status()` raises an `httpx.HTTPStatusError`, the full response (which may include `Authorization` header echoes or URLs carrying credentials) is logged upstream. Wrap the call in a try/except that logs only the status code and URL, not the raw exception string. | Security |
| 2 | `jina_embedder.py` | ~330 | **`default_jql` f-string with `self.project_key`.** `project_key` is sourced from environment config, so the risk is low; however if it ever becomes configurable from a tool parameter, the same JQL injection class applies. Consider quoting the key value: `project = "{self.project_key}"`. | Security |
| 3 | `memory.py` | ~17 | **`_content_fingerprint` uses only 12 hex chars (48 bits).** The fingerprint is used for observability (log correlation), not deduplication, so collision risk is low. But the adjacent `fingerprint.py` uses 16 chars consistently. Standardise to 16 chars (`hexdigest()[:16]`) for uniformity. | Maintainability |
| 4 | `violation_writer.py` | whole file | **`write_violations` is synchronous and calls `db_get_connection()`.** Large audit reports with many findings will block the asyncio event loop while inserting records. Wrap the DB calls in `await anyio.to_thread.run_sync(...)` or convert the writer to use async graph calls to keep the server responsive during bulk audits. | Performance |
| 5 | `task_queue.py` | ~65 | **`TaskQueue` instance is module-level singleton.** `task_queue = TaskQueue(max_concurrent=2)` is created at import time. This makes test isolation difficult (a test that enqueues tasks affects subsequent tests) and means `max_concurrent` cannot be tuned without code changes. Expose the constructor parameters via environment variables or instantiate inside the lifespan where config is available. | Maintainability |
| 6 | `task_queue.py` | ~90 | **`cancel_task` removes task from `self.queue` deque with `deque.remove()`.** `deque.remove()` is O(n). With a large queue this becomes slow. Use `deque` as a filter-on-drain pattern (mark task as `CANCELLED` and skip in `_drain_locked`) rather than O(n) removal. | Performance |
| 7 | `search.py` | ~13 | **`rrf_fuse` accepts `Sequence[tuple[str, float]]` but uses `enumerate` on it.** The function ignores the `float` scores from its inputs entirely, using only rank position for RRF scoring. This is correct RRF behaviour, but the misleading parameter name (`vector_hits`, `fts_hits` imply scores matter) should be documented to clarify that scores from upstream are discarded. | Maintainability |

---

## What Looks Good

- **`violation_writer.py` deduplication** — SHA-256 fingerprint check before insertion is correct and prevents duplicates across multi-run audits. The `seen_fingerprints` parameter allows cross-batch dedup in orchestrated runs.
- **`fingerprint.py` normalisation** — Stripping block comments, line comments, and whitespace before hashing makes fingerprints resilient to cosmetic reformatting. Regex constants are compiled once at module level.
- **`task_queue.py` LRU completed-task eviction** — `_remember_completed` with `_completed_order` deque correctly bounds memory for long-running servers that process many tasks.
- **`summarizer.py` sentinel-based shutdown** — Sending `None` as a sentinel after `queue.join()` ensures all in-flight jobs finish before the worker exits. `run_in_executor` for the blocking Ollama call correctly avoids blocking the event loop.
- **`jina_embedder.py` TTL-based index unloading** — `release_idle_resources()` prevents stale embeddings from consuming memory indefinitely. The `_last_used_at` timestamp is updated on every access.
- **`search.py` RRF fusion** — The implementation correctly uses `_RRF_K = 60` (standard value) and ranks both inputs independently before fusing. Clean and correct.

---

## Verdict

**Request Changes** — The JQL injection in `jina_embedder.py` must be fixed. The credential exposure in exception logs and synchronous graph write in `violation_writer.py` are high-priority. All other items are improvements.
