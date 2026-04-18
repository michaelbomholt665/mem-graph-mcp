# Code Review — Final Summary

**Reviewer:** GitHub Copilot
**Scope:** `src/mem_graph/` (complete codebase)
**Review docs:**
- [001-root-level-package.md](001-root-level-package.md)
- [002-agents-package.md](002-agents-package.md)
- [003-models-package.md](003-models-package.md)
- [004-services-package.md](004-services-package.md)
- [005-tools-package.md](005-tools-package.md)
- [006-providers-package.md](006-providers-package.md)
- [007-resources-package.md](007-resources-package.md)
- [008-observability-package.md](008-observability-package.md)
- [009-evals-package.md](009-evals-package.md)

---

## Overall Verdict

**Request Changes — Critical security findings must be resolved before production deployment.**

The codebase is well-structured, uses modern Python patterns (Pydantic AI, FastMCP 3.0, OpenTelemetry), and has clear architectural intent. However, **seven critical/high-severity security bugs** exist across five packages. Three are SSRF vectors, two are injection attacks, one is unrestricted filesystem access, and one is an unauthenticated REST API surface. All seven require fixes before the server handles untrusted traffic.

---

## Critical & High Findings (must fix)

| # | Severity | Package | Location | Finding |
|---|----------|---------|----------|---------|
| C1 | **Critical** | `tools/filesystem` | `filesystem.py` — all six tools | No root-containment: any LLM with the `filesystem` namespace has read/write access to the entire process filesystem |
| C2 | **Critical** | `server` | `server.py` — Starlette routes | `/dashboard/api/*` and `/file-tree/api/*` routes bypass `StaticTokenVerifier` — unauthenticated REST endpoints |
| C3 | **Critical** | `agents/audit` | `rule_injector_agent.py` — `rule_injector_fetch_external_rules` | SSRF: `endpoint` parameter comes from LLM at runtime; only guard is `if not ctx.deps.external_api_url` |
| C4 | **Critical** | `services` | `jina_embedder.py` — `fetch_issue` | JQL injection: `jql=f"key = {issue_key.strip().upper()}"` — `issue_key` is not validated |
| C5 | **Critical** | `providers` | `openapi.py` — `fetch_spec` | SSRF: `spec_url` accepted without scheme/host validation — any URL is fetched |
| C6 | **Critical** | `agents` | `orchestrator_agent.py` and `audit_agent.py` — `list_files` | Path traversal: `glob.glob` on `package_path` with no containment to project root |
| H1 | **High** | `db` | `db.py` — `db_update_embedding` | Cypher injection via f-string: `f"CALL DROP_VECTOR_INDEX('{table}', '{index_name}')"` — parameters unvalidated |

---

## Recommended Fix Approach (priority order)

### C1 — Filesystem root-containment (`tools/filesystem/filesystem.py`)

Add a validated root constant and resolve+check every path before use:

```python
_FS_ROOT = Path(os.environ.get("MEM_GRAPH_FS_ROOT", ".")).resolve()

def _safe_path(raw: str) -> Path:
    resolved = (_FS_ROOT / raw).resolve()
    if not str(resolved).startswith(str(_FS_ROOT)):
        raise PermissionError(f"Path outside allowed root: {raw}")
    return resolved
```

Apply `_safe_path` to every path argument in `file_read`, `file_write`, `file_edit`, `file_delete`, `file_search`, `file_grep`.

---

### C2 — Unauthenticated Starlette routes (`server.py`)

Add the `auth_api_middleware` (or `StaticTokenVerifier`) to the Starlette sub-application routes. At a minimum, verify `Authorization: Bearer <token>` in each route handler or inject a shared middleware:

```python
from starlette.middleware import Middleware
from .auth import auth_api_middleware

dashboard_app = Starlette(
    routes=[...],
    middleware=[Middleware(BaseHTTPMiddleware, dispatch=auth_api_middleware)],
)
```

---

### C3 — SSRF in rule injector (`agents/audit/rule_injector_agent.py`)

Replace the LLM-supplied `endpoint` parameter with the pre-configured `ctx.deps.external_api_url`:

```python
# Before
async def rule_injector_fetch_external_rules(ctx: RunContext[RuleInjectorDeps], endpoint: str) -> str:

# After
async def rule_injector_fetch_external_rules(ctx: RunContext[RuleInjectorDeps]) -> str:
    endpoint = ctx.deps.external_api_url
    if not endpoint:
        return "No external rules endpoint configured."
```

---

### C4 — JQL injection (`services/jina_embedder.py`)

Validate `issue_key` before interpolation:

```python
import re
_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}-\d{1,6}$")

def _validate_issue_key(key: str) -> str:
    clean = key.strip().upper()
    if not _ISSUE_KEY_RE.match(clean):
        raise ValueError(f"Invalid Jina issue key: {key!r}")
    return clean

# In fetch_issue:
jql = f"key = {_validate_issue_key(issue_key)}"
```

---

### C5 — SSRF in OpenAPI provider (`providers/openapi.py`)

Validate the URL before making the request:

```python
from urllib.parse import urlparse

def _validate_spec_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"}:
        raise ValueError(f"Unsupported scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("Missing hostname in spec_url")
    # Optional: blocklist private IP ranges
```

Close the `httpx.AsyncClient` properly:

```python
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.get(spec_url)
```

---

### C6 — Path traversal in `list_files` (`agents/`)

Resolve the glob base path and assert it is within the project root:

```python
import os
_PROJECT_ROOT = Path(os.environ.get("MEM_GRAPH_PROJECT_ROOT", ".")).resolve()

def _contained_glob(base: str, pattern: str) -> list[str]:
    base_path = (_PROJECT_ROOT / base).resolve()
    if not str(base_path).startswith(str(_PROJECT_ROOT)):
        raise PermissionError(f"Package path outside project root: {base}")
    return glob.glob(str(base_path / "**" / pattern), recursive=True)
```

---

### H1 — Cypher injection in `db_update_embedding` (`db.py`)

Replace free-form `table` / `index_name` interpolation with an allowlist:

```python
_VALID_TABLES = {"Memory", "CodeFile", "Project", "Task"}
_VALID_INDEX_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")

def _validate_table(table: str) -> str:
    if table not in _VALID_TABLES:
        raise ValueError(f"Unknown table: {table!r}")
    return table

def _validate_index_name(name: str) -> str:
    if not _VALID_INDEX_NAME_RE.match(name):
        raise ValueError(f"Invalid index name: {name!r}")
    return name
```

Then use parameterized Cypher where available, or validated interpolation:

```python
conn.execute(
    f"CALL DROP_VECTOR_INDEX('{_validate_table(table)}', '{_validate_index_name(index_name)}')"
)
```

---

## Medium & Low Finding Highlights

The following recurring patterns should be addressed in a follow-up pass:

| Pattern | Locations | Impact |
|---------|----------|--------|
| Dead code (`auth.py` never imported) | `auth.py` | Maintenance confusion |
| `JINA_TOKEN` stored as plain `str` in config | `config.py` | Token visible in memory dumps |
| `auth_api_middleware` and `StaticTokenVerifier` both exist — only one is used | `auth.py`, `server.py` | Dead code |
| `_get_state` stores mutable state on `RunContext` via dynamic attribute | `orchestrator_agent.py` | State may reset between agent calls |
| `all_patches` dict written from concurrent workers without a lock | `orchestrator_graph.py` | Data race |
| `uuid4()` in `models/task.py` (should be `id_generate_v7()`) | `task.py` | Breaks ID ordering assumption |
| `TaskStatus` defined in both `models/task.py` and `models/work.py` | Both | Import ambiguity / name collision |
| Jina auth token visible in `HTTPStatusError` exceptions | `jina_embedder.py` | Token leak in logs/tracebacks |
| `violation_writer.write_violations` is synchronous (blocks event loop) | `violation_writer.py` | Latency spike on large reports |
| Sequential `embeddings_documents` | `embeddings.py` | Slow bulk ingestion |
| `load_node_styles()` reads from disk on every call | `tools/graph/graph_queries.py` | Repeated I/O |
| `httpx.AsyncClient` never closed in `openapi.py` | `providers/openapi.py` | Connection leak |
| `_sanitize_attributes` defined in two observability modules | `logfire_setup.py`, `metrics.py` | DRY violation |
| No timeout on `await runner(case)` in evals | `evaluator.py` | CI hangs |
| Eval suites sequential — no `asyncio.gather` | `evaluator.py` | Slow at scale |

---

## Package-level Verdicts

| Package | Verdict | Critical | High | Medium | Low |
|---------|---------|---------|------|--------|-----|
| Root (`__init__`, `auth`, `config`, `db`, `embeddings`, `server`) | Request Changes | 2 | 1 | 3 | 4 |
| `agents/` | Request Changes | 2 | 0 | 2 | 4 |
| `models/` | Request Changes (minor) | 0 | 0 | 2 | 5 |
| `services/` | Request Changes | 1 | 0 | 3 | 6 |
| `tools/` | Request Changes | 1 | 0 | 2 | 5 |
| `providers/` | Request Changes | 1 | 0 | 1 | 2 |
| `resources/` | Approve with comments | 0 | 0 | 0 | 6 |
| `observability/` | Approve with comments | 0 | 0 | 0 | 6 |
| `evals/` | Approve with comments | 0 | 0 | 2 | 6 |
| **TOTAL** | **Request Changes** | **7** | **1** | **15** | **44** |
