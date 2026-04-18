# Code Review — `src/mem_graph/observability/`

**Reviewer:** GitHub Copilot
**Package:** `src/mem_graph/observability/`
**Files reviewed:**
- `__init__.py`
- `instrumentation.py`
- `logfire_setup.py`
- `metrics.py`
- `otel_setup.py`

---

## Summary

The observability package is one of the cleanest in the codebase. It correctly implements a once-per-process singleton initialisation pattern using `threading.Lock`, handles the Logfire-vs-bare-OTel coexistence case well (provider detection guards), and scrubs bearer tokens from Logfire output. The instrumentation layer logs only argument *count*, not argument values, which is the right call for privacy.

The issues found are all code-quality / maintenance concerns rather than security or correctness bugs. **No critical findings.**

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

### 3. `otel_setup._STATE` never populated when Logfire owns providers — LOW

**Location:** `otel_setup.setup_observability` / `logfire_setup.setup_logfire`

When `setup_logfire` is called, it internally calls `_resolve_otel_state` twice (once inside `_resolve_state`, once explicitly to build `additional_span_processors`). It does **not** call `setup_observability`, so `otel_setup._STATE` remains `None` for the lifetime of the process. Any code that later calls `setup_observability` will re-run the full setup path even though Logfire already owns the providers.

In practice the `_provider_is_logfire` guard in `setup_observability` catches this and returns early, but `_STATE` is still set to a value that says `enabled=True/False` without the providers actually being configured standalone. The state is therefore misleading for any caller that inspects it.

**Suggested fix:** After the early-return guard in `setup_observability`, still persist `_STATE = state` so `shutdown_observability` and any state-readers see a coherent value regardless of which bootstrap path was taken.

---

### 4. Shutdown errors silently swallowed at DEBUG level — LOW

**Location:** `otel_setup.shutdown_observability` lines ~207–230, `logfire_setup.shutdown_logfire` lines ~245–260

All `except Exception` blocks inside both shutdown functions log at `logger.debug(...)`. If the OTLP exporter fails to flush (e.g. network timeout), the operator will never see a warning in production logs unless debug logging is explicitly enabled.

```python
# Current
except Exception as exc:
    logger.debug("Failed to flush tracer provider: %s", exc)

# Suggested
except Exception as exc:
    logger.warning("Failed to flush tracer provider: %s", exc)
```

---

### 5. `ConsoleSpanExporter` writes to `stderr`, `ConsoleMetricExporter` writes to `stdout` — LOW

**Location:** `otel_setup._build_span_processors` / `_build_metric_readers`

The span exporter is explicitly pointed at `sys.stderr`:
```python
ConsoleSpanExporter(out=sys.stderr)
```
while the metric exporter defaults to `stdout`. In a container environment with log aggregation, this splits telemetry across two streams. Both should use the same stream, preferably `sys.stderr`, so telemetry does not mix with application output.

---

### 6. Module-level `_LOGFIRE` created before `logfire.configure()` — INFO

**Location:** `logfire_setup.py` line ~18

```python
_LOGFIRE = logfire.with_tags("mem_graph")
```

This is assigned at import time, before `setup_logfire` is called. Logfire's lazy-proxy design means this works correctly in practice, but it is a dependency on an implementation detail of the Logfire library. If Logfire ever stops lazily proxying the global state after `with_tags()`, this will silently emit untagged spans.

**Suggested fix:** Assign `_LOGFIRE` inside `setup_logfire` immediately after `logfire.configure()`, or document the dependency explicitly with a comment.

---

### 7. `inspect.iscoroutinefunction` check in `traced_tool` will miss `functools.partial` wrapping — LOW

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
| 3 | Low | `otel_setup.setup_observability` | `_STATE` never set when Logfire owns providers |
| 4 | Low | Both shutdown functions | Errors swallowed at DEBUG instead of WARNING |
| 5 | Low | `otel_setup._build_*` | Span→stderr, metrics→stdout inconsistency |
| 6 | Info | `logfire_setup.py:18` | `_LOGFIRE` created before `logfire.configure()` |
| 7 | Low | `instrumentation.traced_tool` | `functools.partial` async functions use sync path |
