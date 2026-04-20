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

The observability package is structurally solid: it centralizes setup, keeps graph-query payloads out of telemetry, and uses one-time process state to avoid duplicate initialization. The main problems are lifecycle edge cases and overly permissive attribute serialization. The highest-signal bug is that Logfire transport detection reads the wrong environment variable.

---

## Issues

### 1. Logfire stdio detection reads `TRANSPORT`, but the app config uses `MCP_TRANSPORT` — MEDIUM

**Location:** `logfire_setup.py:144-145`

`setup_logfire()` decides whether it is running over stdio with:

```python
is_stdio = os.getenv("TRANSPORT", "stdio") == "stdio"
```

Everywhere else in the app, transport is configured through `MCP_TRANSPORT` (`app/constants.py`). As written, Logfire will usually ignore the real transport setting and fall back to `"stdio"`.

That means console/metrics behavior can silently be wrong in HTTP mode, and any transport-specific observability tuning is keyed off the wrong source of truth.

**Suggested fix:** Read `MCP_TRANSPORT` (or import the resolved app constant) instead of `TRANSPORT`.

---

### 2. Both setup functions publish `_STATE` before initialization is fully complete — MEDIUM

**Location:** `logfire_setup.py:137-142`, `otel_setup.py:155-160`

`setup_logfire()` and `setup_observability()` assign the module-global `_STATE` before configuration work is finished. If later steps throw, future setup calls will see a non-`None` state and incorrectly assume initialization already succeeded.

This creates a sticky partial-init failure mode that is hard to recover from inside a long-lived process or test run.

**Suggested fix:** Only assign `_STATE` after successful initialization, or reset it inside an exception handler before re-raising.

---

### 3. Telemetry attribute sanitization falls back to `str(value)` for arbitrary objects — MEDIUM

**Location:** `instrumentation.py:33-39`, `logfire_setup.py:118-125`, `metrics.py:49-56`

All three sanitization paths stringify unknown objects. That is convenient, but it also means telemetry will happily ingest whatever a custom `__str__`/`__repr__` returns.

In practice this risks:

- leaking secret-bearing object representations into traces/logs/metrics
- creating unbounded or high-cardinality attribute values
- making “sanitized” behavior look safer than it really is

**Suggested fix:** Restrict attributes to primitive allowlisted types and replace everything else with a bounded placeholder such as `"<non-serializable>"` or a type name.

---

### 4. Shutdown does not clear process state, so re-initialization in the same process is skipped — LOW

**Location:** `logfire_setup.py:245-259`, `otel_setup.py:201-234`

`shutdown_logfire()` and `shutdown_observability()` flush/shutdown providers, but they never set `_STATE = None`. If the same Python process later calls `setup_*()` again, the cached state short-circuits reinitialization.

That is mostly a testability and long-running-process problem, but it is a real lifecycle footgun.

**Suggested fix:** Clear the cached state after a successful shutdown or document these modules as single-init, single-shutdown only.

---

### 5. Shutdown paths suppress all flush/shutdown failures at debug level only — LOW

**Location:** `logfire_setup.py:251-259`, `otel_setup.py:215-234`

The shutdown paths intentionally avoid raising, which is fine, but every failure is swallowed into a debug log. In practice that makes dropped telemetry or broken exporter shutdown easy to miss in production.

**Suggested fix:** Keep the non-raising behavior, but consider warning-level logs when flushing or shutdown fails.

---

## Positive Observations

- Graph-query observability is careful not to emit raw query text or raw parameters.
- The package keeps setup and usage paths separate, which makes the instrumentation surface easy to reason about.
- `traced_tool()` consistently records success/failure, duration, and exception metadata for both sync and async code paths.
- OpenTelemetry setup correctly avoids stomping on an already-configured non-default provider.

---

## Verdict

**Approve with comments.** The package is well organized, but I would fix the transport-source bug and the partial-initialization state handling before relying on these helpers across multiple runtimes or test processes.
