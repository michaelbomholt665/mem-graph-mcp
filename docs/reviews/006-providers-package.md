# Code Review: `src/mem_graph/providers/`

**Reviewed:** 2026-04-14
**Scope:** `openapi.py`

---

## Summary

The providers package is minimal — a single file that fetches an OpenAPI spec and constructs a FastMCP `OpenAPIProvider`. The code is clean and correctly delegates to the FastMCP library. (Note: Critical SSRF risk and HTTP client lifecycle issues are now covered in 015-providers-review.md).

---

## Critical Issues

_None._ (Previous critical issues are now documented in 015-providers-review.md)

---

## Suggestions

| # | File | Line | Suggestion | Category |
|---|------|------|------------|----------|
| 1 | `openapi.py` | ~26 | **Spec size not limited.** A very large or intentionally slow OpenAPI spec at the configured URL will consume unbounded memory during `resp.json()`. Add a `max_response_size` guard (e.g., reject specs > 10 MB). | Performance |
| 2 | `openapi.py` | ~26 | **`resp.json()` can raise `json.JSONDecodeError`** (e.g., if the server returns HTML on error, or the URL points to a non-JSON resource). This exception bubbles to `_load_openapi_providers` where it is caught broadly and logged as a warning. Add explicit error handling here to distinguish `JSONDecodeError` from HTTP errors and log a more actionable message. | Correctness |

---

## What Looks Good

- **Security comment in module docstring** — Explicitly advising operators to strip admin and DELETE routes from specs before ingestion is a useful, actionable warning.
- **Shared `httpx.AsyncClient`** — Using a single persistent client for all provider tool calls (rather than a new client per request) is the correct performance pattern.
- **Graceful failure in `_load_openapi_providers`** (server.py) — Failures to load individual providers are caught and logged as warnings, not crashes.

---

## Verdict

**Request Changes** — The SSRF risk should be mitigated with URL scheme validation. The unclosed client is a resource leak that should be fixed for long-running deployments.
