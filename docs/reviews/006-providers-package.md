# Code Review: `src/mem_graph/providers/`

**Reviewed:** 2026-04-14
**Scope:** `openapi.py`

---

## Summary

The providers package is minimal — a single file that fetches an OpenAPI spec and constructs a FastMCP `OpenAPIProvider`. The code is clean and correctly delegates to the FastMCP library. Two issues are noted: an SSRF risk from unconstrained `spec_url` values and a long-lived HTTP client that is never closed.

---

## Critical Issues

| # | File | Line | Issue | Severity |
|---|------|------|-------|----------|
| 1 | `openapi.py` | ~26 | **SSRF via unconstrained `spec_url`.** `fetch_spec(spec_url)` issues an HTTP GET to any URL supplied by the `MEM_GRAPH_OPENAPI_SPECS` environment variable. While this is an operator-supplied value today, a misconfigured or compromised deployment could point this at an internal metadata endpoint (e.g., `http://169.254.169.254/latest/meta-data/`). Validate `spec_url` at parse time — only allow `https://` scheme and, optionally, an allowlist of trusted domains. | 🔴 Critical |

---

## Suggestions

| # | File | Line | Suggestion | Category |
|---|------|------|------------|----------|
| 1 | `openapi.py` | ~43 | **`httpx.AsyncClient` is created but never explicitly closed.** The client is passed to `OpenAPIProvider` and held for the provider's lifetime, but there is no close/cleanup path if the provider is removed or the server shuts down. Either register the client for cleanup in the lifespan, or use `OpenAPIProvider`'s built-in client management if it supports it. | Correctness |
| 2 | `openapi.py` | ~26 | **Spec size not limited.** A very large or intentionally slow OpenAPI spec at the configured URL will consume unbounded memory during `resp.json()`. Add a `max_response_size` guard (e.g., reject specs > 10 MB). | Performance |
| 3 | `openapi.py` | ~9 | **Security note references CVE-2026-32871 but does not enforce the minimum version.** The comment advises `fastmcp>=3.2.3` but `pyproject.toml` may not pin this. Verify the dependency constraint is actually enforced in `pyproject.toml`. If the pin is missing, add it. | Security |
| 4 | `openapi.py` | ~26 | **`resp.json()` can raise `json.JSONDecodeError`** (e.g., if the server returns HTML on error, or the URL points to a non-JSON resource). This exception bubbles to `_load_openapi_providers` where it is caught broadly and logged as a warning. Add explicit error handling here to distinguish `JSONDecodeError` from HTTP errors and log a more actionable message. | Correctness |

---

## What Looks Good

- **Security comment in module docstring** — Explicitly advising operators to strip admin and DELETE routes from specs before ingestion is a useful, actionable warning.
- **Shared `httpx.AsyncClient`** — Using a single persistent client for all provider tool calls (rather than a new client per request) is the correct performance pattern.
- **Graceful failure in `_load_openapi_providers`** (server.py) — Failures to load individual providers are caught and logged as warnings, not crashes.

---

## Verdict

**Request Changes** — The SSRF risk should be mitigated with URL scheme validation. The unclosed client is a resource leak that should be fixed for long-running deployments.
