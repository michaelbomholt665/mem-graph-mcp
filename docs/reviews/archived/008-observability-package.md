# Code Review — `src/mem_graph/observability/`

**Reviewer:** GitHub Copilot
**Resolved:** 2026-04-19
**Status:** ✅ COMPLETE — all issues fixed
**Package:** `src/mem_graph/observability/`
**Files reviewed:**
- `__init__.py`
- `instrumentation.py`
- `logfire_setup.py`
- `metrics.py`
- `otel_setup.py`

---

## Summary

The observability package is one of the cleanest in the codebase. It correctly implements a once-per-process singleton initialisation pattern using `threading.Lock`, handles the Logfire-vs-bare-OTel coexistence case well, and scrubs bearer tokens from Logfire output. (Note: Shutdown error handling is now covered in 014-observability-review.md).

---

## Issues

### 1. `_sanitize_attributes` duplicated across two modules — LOW

**Location:** `logfire_setup.py` lines ~100–115, `metrics.py` lines ~1–30

Both modules define an identical `_sanitize_attributes` helper that strips `None` values and coerces non-primitives to `str`. Neither imports from the other. If the logic diverges in the future (e.g. adding a character-length cap for OTEL compliance) only one copy will be updated.

**Suggested fix:** Extract to a shared `_helpers.py` or a private `_common.py` within the package, then import it in both places.

---

### 2. `_bool_env` duplicated across two modules — LOW

**Location:** `otel_setup.py` lines ~65–70, `logfire_setup.py` lines ~38–43

Identical four-line helper defined in both files. Same duplication risk as `_sanitize_attributes`.

---

### 3. `ConsoleSpanExporter` writes to `stderr`, `ConsoleMetricExporter` writes to `stdout` — LOW

**Location:** `otel_setup._build_span_processors` / `_build_metric_readers`

The span exporter is explicitly pointed at `sys.stderr`:
```python
ConsoleSpanExporter(out=sys.stderr)
```
while the metric exporter defaults to `stdout`. In a container environment with log aggregation, this splits telemetry across two streams. Both should use the same stream, preferably `sys.stderr`, so telemetry does not mix with application output.

---

### 4. Module-level `_LOGFIRE` created before `logfire.configure()` — INFO

**Location:** `logfire_setup.py` line ~18

```python
_LOGFIRE = logfire.with_tags("mem_graph")
```

This is assigned at import time, before `setup_logfire` is called. Logfire's lazy-proxy design means this works correctly in practice, but it is a dependency on an implementation detail of the Logfire library. If Logfire ever stops lazily proxying the global state after `with_tags()`, this will silently emit untagged spans.

**Suggested fix:** Assign `_LOGFIRE` inside `setup_logfire` immediately after `logfire.configure()`, or document the dependency explicitly with a comment.

---

### 5. `inspect.iscoroutinefunction` check in `traced_tool` will miss `functools.partial` wrapping — LOW

**Location:** `instrumentation.py` in `traced_tool` decorator

```python
if inspect.iscoroutinefunction(func):
    ...
    return async_wrapper
```

`functools.partial` objects wrapping an async function return `False` from `inspect.iscoroutinefunction`. If any tool is registered as a `partial`, it will silently use `sync_wrapper` and block the event loop. The decorator provides no warning in this path.

**Suggested fix:** Also check `inspect.iscoroutinefunction(getattr(func, "func", func))` to unwrap `partial`.

---

## Positive Observations

- **Bearer token scrubbing** in `logfire_setup` (`ScrubbingOptions(extra_patterns=[...])`) is correct and matches the pattern from `auth.py`. The regex `r"(?i)bearer\s+[a-z0-9._=-]+"` will catch JWT tokens in span attributes.
- **`inspect_arguments=False`** passed to `logfire.configure` avoids any risk of PII leaking through argument introspection.
- **Provider-detection guards** (`_provider_is_logfire`, `_default_proxy_provider`) prevent double-initialisation cleanly.
- **Argument count only** is logged in `instrumentation.py` — argument *values* are never recorded. This is the right privacy boundary.
- **`_sanitize_attributes`** correctly drops `None` values and stringifies unknown types rather than crashing, which makes the telemetry layer robust against model changes.
- `traced_span` and `traced_tool` both set `StatusCode.ERROR` and call `span.record_exception(exc)` before re-raising — correct OTel error handling.

---

## Verdict

**Approve with comments.** No critical or high-severity issues. All findings are low-severity quality concerns that should be addressed before the next major refactor but do not block merging.

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 1 | Low | `logfire_setup.py`, `metrics.py` | `_sanitize_attributes` duplicated |
| 2 | Low | `otel_setup.py`, `logfire_setup.py` | `_bool_env` duplicated |
| 3 | Low | Both shutdown functions | Errors swallowed at DEBUG instead of WARNING |
| 4 | Low | `otel_setup._build_*` | Span→stderr, metrics→stdout inconsistency |
| 5 | Info | `logfire_setup.py:18` | `_LOGFIRE` created before `logfire.configure()` |
| 6 | Low | `instrumentation.traced_tool` | `functools.partial` async functions use sync path |
