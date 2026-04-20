# `mem_graph.app` — Refactor Proposal

## Current Layout

```
app/
├── __init__.py          # empty docstring
├── auth.py              # StaticTokenVerifier + build_auth_provider()
├── constants.py         # env-derived config, server metadata, banner
├── lifespan.py          # server lifespan, startup/shutdown wiring, banner printing
├── middleware.py         # LoggingMiddleware (MCP tool-call logging)
├── prompts.py           # MCP prompt registrations
├── registry.py          # AgentEntry dataclass + sub-agent registry
├── resources.py         # MCP resource template handlers (memory, task, project, violation)
├── telemetry.py         # dashboard graph telemetry queries (node/edge counts)
├── tools.py             # server-info payload, tool catalog, namespace activation, MCP tool registrations
├── web.py               # Starlette routes, dashboard API handlers, HTTP app builder
└── parsers/             # well-structured sub-package
    ├── __init__.py
    ├── assets.py
    ├── extractors/
    ├── ingest.py
    ├── loader.py
    ├── persist.py
    ├── pipeline.py
    ├── query_codegen.py
    ├── query_validate.py
    ├── resolvers/
    ├── safety.py
    └── types.py
```

## Problem

The top-level `app/` files mix several distinct concerns:

| Concern | Files | Description |
|---|---|---|
| **Server config & startup** | `constants.py`, `lifespan.py` | env vars, host/port, banner, lifespan context |
| **HTTP / dashboard layer** | `web.py`, `telemetry.py` | Starlette routes, dashboard API handlers, graph telemetry queries |
| **MCP surface registrations** | `prompts.py`, `resources.py`, `tools.py` | registering prompts, resources, and tools on FastMCP |
| **Auth & middleware** | `auth.py`, `middleware.py` | token verification, MCP call logging |
| **Agent / discovery metadata** | `registry.py` | sub-agent registry dataclass + in-memory store |

`web.py` (439 lines) and `tools.py` (189 lines) are the heaviest files. `web.py` bundles route definitions, dashboard JSON handlers, static-file serving, and the `build_http_app()` factory. `tools.py` bundles server metadata helpers, tool catalog logic, namespace activation, and MCP tool registration — three loosely related responsibilities.

## Proposed Layout

```
app/
├── __init__.py              # re-exports create_app() or build_server()
├── app.py                   # main entry: wires FastMCP + Starlette, calls register_* and build_http_app
├── config.py                # constants.py renamed; env-derived config, banner strings, LAZY_NAMESPACES
├── lifespan.py              # unchanged (already focused)
│
├── auth/
│   ├── __init__.py          # re-exports build_auth_provider, StaticTokenVerifier
│   ├── provider.py          # StaticTokenVerifier + build_auth_provider() (from auth.py)
│   └── middleware.py        # LoggingMiddleware (from middleware.py)
│
├── http/
│   ├── __init__.py          # re-exports build_http_app
│   ├── app.py               # build_http_app() factory (from web.py)
│   ├── routes.py            # route list + Starlette wiring (from web.py)
│   ├── dashboard.py         # dashboard/system/agents/workflows/evals/graph/search handlers (from web.py)
│   ├── health.py            # _info(), _health() handlers (from web.py)
│   ├── static_files.py      # _dashboard(), _explore(), _agents(), _tools(), _evals(), _file_tree(), JS/CSS (from web.py)
│   ├── file_tree.py         # _file_tree_data(), _file_tree_violations() (from web.py)
│   └── telemetry.py         # query_rows(), safe_count(), dashboard_graph_telemetry() (from telemetry.py)
│
├── mcp/
│   ├── __init__.py          # re-exports register_all()
│   ├── prompts.py           # unchanged (from prompts.py)
│   ├── resources.py         # unchanged (from resources.py)
│   ├── tools.py             # register_tools() + namespace activation only (slimmed from tools.py)
│   └── catalog.py           # catalog_tools(), get_namespace(), server_info_payload(), list_agents(), list_task_types(), system_inspect() (from tools.py)
│
├── registry.py              # unchanged (small, self-contained; move into mcp/ if preferred)
│
└── parsers/                 # unchanged
```

## File-by-File Mapping

### New `app/app.py` — main application assembly

Composes the server from sub-packages. Replaces the scattered `from .tools import register_tools` / `from .prompts import register_prompts` imports that currently live in `server.py` or `lifespan.py`.

```python
# app/app.py — pseudo-code outline
from .config import ...
from .lifespan import build_lifespan
from .auth import build_auth_provider
from .auth.middleware import LoggingMiddleware
from .mcp import register_prompts, register_resources, register_tools
from .http import build_http_app

def create_server() -> FastMCP:
    mcp = FastMCP(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        auth=build_auth_provider(),
        lifespan=build_lifespan,
        middleware=[LoggingMiddleware()],
    )
    register_prompts(mcp)
    register_resources(mcp)
    register_tools(mcp)
    return mcp

def create_http_app(mcp: FastMCP) -> Starlette:
    return build_http_app(mcp)
```

### `auth/` sub-package

| Source | Target | What moves |
|---|---|---|
| `auth.py` | `auth/provider.py` | `StaticTokenVerifier`, `build_auth_provider()` |
| `middleware.py` | `auth/middleware.py` | `LoggingMiddleware` |

Both files deal with request-level gatekeeping — token verification and call logging are two sides of the same "who is calling and what did they do" concern.

### `http/` sub-package

| Source | Target | What moves |
|---|---|---|
| `web.py` → `build_http_app()` | `http/app.py` | factory function + combined_lifespan |
| `web.py` → route list | `http/routes.py` | `web_routes` list, `_parse_int`, `_query_flag` |
| `web.py` → `_dashboard_*` handlers | `http/dashboard.py` | `_dashboard_system`, `_dashboard_agents`, `_dashboard_workflows`, `_dashboard_evals`, `_dashboard_graph`, `_dashboard_node`, `_dashboard_search`, `_dashboard_styles`, `dashboard_tools_handler` |
| `web.py` → `_info`, `_health` | `http/health.py` | health and info endpoints |
| `web.py` → static page handlers | `http/static_files.py` | `_dashboard`, `_explore`, `_agents`, `_tools`, `_evals`, `_file_tree`, `_dashboard_js`, `_dashboard_css`, `_force_graph_js` |
| `web.py` → file tree handlers | `http/file_tree.py` | `_file_tree_data`, `_file_tree_violations` |
| `telemetry.py` | `http/telemetry.py` | `query_rows`, `safe_count`, `dashboard_graph_telemetry`, private helpers |

`telemetry.py` is only consumed by `web.py` dashboard handlers — it is a data-access layer for the HTTP dashboard, not a shared service. Moving it into `http/` makes that clear.

### `mcp/` sub-package

| Source | Target | What moves |
|---|---|---|
| `prompts.py` | `mcp/prompts.py` | unchanged |
| `resources.py` | `mcp/resources.py` | unchanged |
| `tools.py` → `register_tools`, `tools_activate` | `mcp/tools.py` | registration + namespace activation |
| `tools.py` → rest | `mcp/catalog.py` | `server_info_payload`, `get_server_info`, `get_namespace`, `catalog_tools`, `list_agents`, `list_task_types`, `system_inspect`, `mcp_memory_system_inspect` |

`tools.py` currently serves two roles: (1) MCP tool registration and namespace activation, and (2) server metadata / discovery helpers consumed by `web.py`. Splitting into `mcp/tools.py` (registration) and `mcp/catalog.py` (read-only catalog/metadata) separates the "write" side (registering tools, activating namespaces) from the "read" side (inspecting what is registered).

### `registry.py`

Small and self-contained (41 lines). Can stay at `app/registry.py` or move into `mcp/` since `AgentEntry` is only consumed by `mcp/catalog.py`. Either is fine; the proposal keeps it at the top level for now to minimize churn.

## What Does NOT Move

| File | Reason |
|---|---|
| `config.py` (renamed from `constants.py`) | Single file, env-derived config is already cohesive. Rename only. |
| `lifespan.py` | Already focused on startup/shutdown lifecycle. Imports from many places but is itself a leaf. |
| `parsers/` | Already well-structured with its own sub-packages. |
| `registry.py` | 41 lines, single concern. Not worth a sub-package. |

## Import Impact

Most consumer imports shift from:

```python
from mem_graph.app.web import build_http_app
from mem_graph.app.auth import build_auth_provider
from mem_graph.app.middleware import LoggingMiddleware
from mem_graph.app.tools import catalog_tools, server_info_payload
from mem_graph.app.telemetry import dashboard_graph_telemetry
```

To:

```python
from mem_graph.app.http import build_http_app
from mem_graph.app.auth import build_auth_provider
from mem_graph.app.auth.middleware import LoggingMiddleware
from mem_graph.app.mcp.catalog import catalog_tools, server_info_payload
from mem_graph.app.http.telemetry import dashboard_graph_telemetry
```

Each sub-package `__init__.py` should re-export the public API so most call sites can use the shorter form (`from mem_graph.app.http import build_http_app`).

## Suggested Execution Order

1. **Rename `constants.py` → `config.py`** and update all imports. Low risk.
2. **Extract `auth/` sub-package.** Two files, no logic changes.
3. **Extract `mcp/` sub-package.** Move `prompts.py`, `resources.py`, `tools.py` → split into `mcp/tools.py` + `mcp/catalog.py`. Update `server.py` to import from new locations.
4. **Extract `http/` sub-package.** Decompose `web.py` into 5–6 focused modules. Move `telemetry.py` into `http/`.
5. **Create `app/app.py`.** Wire everything together in one place.
6. **Update `app/__init__.py`.** Re-export `create_server` / `create_http_app` so external consumers (main.py, tests) need minimal changes.
7. **Run full test suite + lint + mypy** after each step.
