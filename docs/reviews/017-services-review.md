# Code Review — `src/mem_graph/services/`

**Reviewer:** GitHub Copilot
**Resolved:** 2026-04-19
**Status:** ✅ COMPLETE — all issues fixed
**Package:** `src/mem_graph/services/`
**Files reviewed:**
- `__init__.py`
- `code_embed_service.py`
- `fingerprint.py`
- `jina_common.py`
- `jina_embedder.py`
- `memory.py`
- `report_writer.py`
- `search.py`
- `summarizer.py`
- `task_queue.py`
- `text_embed_service.py`
- `violation_writer.py`

---

## Summary

This folder contains several of the highest-impact runtime helpers in the repo: the background summarizer, task queue, memory persistence, audit deduplication, and Jina/code matching services. The overall structure is decent, but I found a handful of real operational hazards: shutdown can hang, queued task runners can leak, fingerprint lookup can silently degrade into duplicate-violation creation, and one file-lookup path escapes its intended root boundary.

---

## Issues

### 1. Summarizer shutdown can hang indefinitely despite the docstring promising a timeout — MEDIUM

**Location:** `summarizer.py:64-80`

`stop_worker()` says it “awaits completion (up to 30 s)”, but the implementation does:

```python
await _queue.join()
await _queue.put(None)
await _worker_task
```

There is no timeout anywhere. If the worker is stuck in `_process()` or an Ollama/embedding path never returns, server shutdown can block forever.

**Suggested fix:** Wrap the drain/wait sequence in `asyncio.wait_for()` and cancel the worker if the timeout is exceeded.

---

### 2. `TaskQueue.shutdown()` cancels queued tasks but leaves their runner callables in `_runners` — MEDIUM

**Location:** `task_queue.py:77-110`

During shutdown, queued task IDs are marked cancelled and remembered as completed, but their entries are never removed from `self._runners`. Only running tasks clean up `_runners` in `_run_task()`’s `finally` block.

That means queued-but-never-started tasks keep their captured runner closures alive until process exit or later pruning side effects.

**Suggested fix:** Remove queued task IDs from `_runners` during shutdown, the same way `cancel_task()` already does for pre-start cancellation.

---

### 3. Fingerprint lookup treats every DB error as “schema too old”, which can create duplicate violations — MEDIUM

**Location:** `violation_writer.py:115-130`

`_violation_find_by_fingerprint()` catches all exceptions and returns `None`, with a comment that this means the fingerprint column is missing. That fallback is too broad: a transient DB failure, syntax issue, or unexpected query result will be interpreted as “no match found”.

The caller then creates a fresh violation node, which can silently multiply duplicates during outages or regressions.

**Suggested fix:** Catch only the specific schema-compatibility failure you expect; log and re-raise unexpected query errors.

---

### 4. `find_tickets_for_file()` resolves relative paths but never enforces that the resolved file stays under the chosen root — MEDIUM

**Location:** `text_embed_service.py:194-199`

For relative input, the service does:

```python
resolved_path = (root / file_path).resolve()
```

It then only checks `exists()` and `is_file()`. A path like `../../outside.txt` can escape the intended project root and still be processed if it exists.

**Suggested fix:** After resolving, verify the file is still under `root` before reading or indexing it.

---

### 5. Code indexing performs blocking filesystem work inside async flows — LOW

**Location:** `code_embed_service.py:92-159`

`ensure_code_index()` and `index_single_file()` are async, but directory walking uses `os.walk()` and file reads use synchronous `Path.read_bytes()`. On large trees or slow disks, that blocks the event loop while an ostensibly async service is running.

**Suggested fix:** Either move the scan/read path behind `to_thread.run_sync()` or make it explicit that indexing is synchronous work wrapped by an async API.

---

## Positive Observations

- `TaskQueue` keeps a clear separation between queued, running, and completed task state.
- `MemoryService` is careful to log only content length/fingerprint rather than raw memory content.
- `report_writer.py` is clean and deterministic; its grouping/bucketing logic is easy to follow.
- The Jina helpers are reasonably well-factored between common types, code indexing, and issue matching.

---

## Verdict

**Request changes.** None of the issues are catastrophic on their own, but the shutdown hang, duplicate-violation fallback, and root-boundary escape are important enough that I would fix them before expanding these services’ use in production workflows.
