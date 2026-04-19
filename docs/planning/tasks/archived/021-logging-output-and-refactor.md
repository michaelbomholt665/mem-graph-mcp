# Task: Optimize Logging Output and Fix Cypher Catalog Exception

## Problem Description

The terminal output is currently flooded with verbose logging during dashboard usage, making it difficult to monitor the server effectively. Specifically:

1.  **Redundant `graph.query` logs**: Every database interaction emits a `graph.query` log line, resulting in dozens of nearly identical lines when the UI refreshes (e.g., dashboard telemetry, graph explorer loading).
2.  **Cypher Catalog Exception**: A `RuntimeError: Catalog exception: function TYPE does not exist` is triggered repeatedly. This is likely caused by an incompatible Cypher function call in `server.py` being executed during telemetry aggregation.

### Example Logs

```text
14:43:36.109 graph.query
14:43:36.114 graph.query
14:43:36.126 graph.query
14:43:36.132   Graph query failed [mem_graph]
             │ RuntimeError: Catalog exception: function TYPE does not exist.
             │ Traceback (most recent call last):
             │   File "/home/michael/projects/python/memory/src/mem_graph/db.py", line 117, in execute
             │     raw_result = self._connection.execute(query, params or {})
             │   File "/home/michael/projects/python/memory/.venv/lib/python3.14/site-packages/real_ladybug/connection.py", line 132, in execute
             │     query_result_internal = self._connection.query(query)
             │ RuntimeError: Catalog exception: function TYPE does not exist.
```

## Proposed Solutions

### 1. Fix the `TYPE()` function call
The `TYPE(r)` function is likely not supported by the current Kuzu/Ladybug version.
- **Location**: `src/mem_graph/server.py` (line 914)
- **Fix**: Replace `TYPE(r)` with `LABEL(r)` or the appropriate relational type accessor for the current schema manager.

### 2. Silence verbose telemetry logs
The telemetry queries are useful for observability but don't need to emit separate terminal lines during every dashboard heartbeat.
- **Action**: Lower the log level for standard `graph.query` spans or filter them out of the console exporter.
- **Action**: Consolidate remaininig telemetry queries to further reduce the number of calls.

### 3. Logfire Optimization
- Ensure that repetitive telemetry queries are marked as "internal" or "system" to reduce noise in the Logfire dashboard.

## Tasks
-[x] Investigate `real_ladybug` Cypher compatibility for relationship types.
-[x] Refactor `server.py` telemetry to use supported Cypher syntax.
-[x] Update `db.py` or logging configuration to suppress `graph.query` console output unless an error occurs.
-[x] Verify that Logfire remains useful but less noisy.

## Refactor `server.py` into `app/` package

The goal is to reduce the footprint of `src/mem_graph/server.py` from 1300+ lines to just enough logic to initialize and run the server. All helper logic will be moved to a new `src/mem_graph/app/` package, adhering to the principle of "one main concern per file."

### Sub-Tasks

-[x] **Initialize `src/mem_graph/app/` package**:
    - Create `src/mem_graph/app/__init__.py`.
-[x] **Extract Constants and Configuration**:
    - [NEW] `src/mem_graph/app/constants.py`: Define `SERVER_NAME`, `SERVER_VERSION`, `_LAZY_NAMESPACES`, `_DEPRECATED_NAMESPACES`, and environment-derived variables like `_HOST`, `_PORT`.
-[x] **Extract Auth Logic**:
    - [NEW] `src/mem_graph/app/auth.py`: Move `StaticTokenVerifier` and its initialization.
-[x] **Extract Middleware**:
    - [NEW] `src/mem_graph/app/middleware.py`: Move `LoggingMiddleware`.
-[x] **Extract Lifespan and Background Services**:
    - [NEW] `src/mem_graph/app/lifespan.py`: Move `lifespan` context manager, `_load_openapi_providers`, and worker start/stop logic.
-[x] **Extract Internal Tools**:
    - [NEW] `src/mem_graph/app/tools.py`: Move `get_server_info`, `tools_search`, `tools_activate`, and the scoring/namespace helpers.
-[x] **Extract MCP Resources**:
    - [NEW] `src/mem_graph/app/resources.py`: Move all `@mcp.resource` definitions (`resource_memory`, `resource_task`, etc.).
-[x] **Extract MCP Prompts**:
    - [NEW] `src/mem_graph/app/prompts.py`: Move all `@mcp.prompt` definitions.
-[x] **Extract Web Framework and Dashboard Logic**:
    - [NEW] `src/mem_graph/app/web.py`: Move Starlette routes, `build_http_app`, and static file responses (`_dashboard`, `_explore`, etc.).
-[x] **Extract Telemetry and DB Helpers**:
    - [NEW] `src/mem_graph/app/telemetry.py`: Move `_dashboard_graph_telemetry`, `_query_rows`, `_safe_count`, and related dashboard API handlers.
-[x] **Refactor `src/mem_graph/server.py`**:
    - Simplify to exactly one responsibility: Initialize the `FastMCP` instance using the extracted components and start the `uvicorn` server.
    - Ensure it produces a clean, structured log output on startup, including the ASCII `_BANNER` logo.
    - Wire all extracted components (auth, middleware, lifespan, routes) into the main app.
-[x] **Validation**:
    - Ensure all dashboard pages (Dashboard, Explore, Agents, Tools, Files) remain fully functional.
    - Verify that the terminal output is clean and the logo is displayed correctly.

## Refactor `jina_embedder.py` into Specialized Services

The `src/mem_graph/services/jina_embedder.py` file has grown to over 800 lines and mixes Jina API interaction, code file indexing, and complex semantic matching logic. We will split this into more granular services while maintaining the existing `jina_embedder.py` as a facade/entry point.

### Sub-Tasks

-[x] **Extract Shared Models and Utilities**:
    - [NEW] `src/mem_graph/services/jina_common.py`: Move shared data classes/models (`JinaIssue`, `CodeMatch`, `TicketMatch`, `IndexedCodeFile`) and low-level utilities (`_flatten_description`, `_cosine_similarity`, `_extract_snippet`).
-[x] **Extract Code Embedding Logic**:
    - [NEW] `src/mem_graph/services/code_embed_service.py`: Focus on local filesystem traversal, code file indexing, and `CodeFile` node persistence. This service will primarily use the `jina-embeddings-v4` model (via `embeddings_code`).
-[x] **Extract Text/Issue Embedding Logic**:
    - [NEW] `src/mem_graph/services/text_embed_service.py`: Focus on Jina API interaction (`fetch_issues`), `JinaIssue` node persistence, and tissue-to-code matching logic. This service will leverage the `nomic-embed-text` model where appropriate (via `embeddings_generate` / `embeddings_query`).
-[x] **Refactor `src/mem_graph/services/jina_embedder.py`**:
    - Convert `JinaCodeEmbedder` into a facade that delegates to the specialized sub-services.
    - Properly coordinate the usage of code vs text models for cross-domain matching.
-[x] **Validation**:
    - Verify that Jina issue syncing still works via the `integrations` namespace.
    - Verify that semantic "Find Code for Issue" and "Find Tickets for File" features remain functional.
