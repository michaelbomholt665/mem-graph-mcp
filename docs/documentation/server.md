# Server Component Documentation

## Purpose
This document explains the Syntx Memory MCP Server component - the foundation that provides the Model Context Protocol (MCP) server interface, handles tool discovery, manages lazy namespace activation, and orchestrates HTTP/SSE transport mechanisms.

## Overview
The server is implemented in `src/mem_graph/server.py` and serves as the entry point for all MCP interactions. It uses the FastMCP framework to provide a standardized interface for tools and agents while implementing custom logic for lazy tool loading, session-based namespace activation, background-task queueing, and dashboard route mounting.

### Responsibilities
- Initialize and shutdown database connections via lifespan management
- Mount all tool sub-servers as namespaced components
- Provide tool discovery mechanisms (`tools_search`, `tools_activate`)
- Handle HTTP and SSE transport protocols
- Manage component visibility through tag-based enabling/disabling
- Ollama model probing and management during startup
- Manage the in-memory background task queue lifecycle
- Expose the lightweight graph dashboard and its JSON APIs

## Architecture Details

### Server Lifecycle
The server uses FastMCP's lifespan context manager to handle initialization and cleanup:

1. **Startup** (`lifespan` function):
   - Calls `db_init_engine()` from `src/mem_graph/db.py` to initialize Ladybug database
   - Installs and loads vector/fts extensions
   - Runs schema DDL from `schema/agent_memory_schema.cypher`
   - Creates vector indexes for all embeddable node types
   - Probes Ollama availability and pulls required embedding model if missing
   - Starts the in-memory background task queue

2. **Runtime**:
   - Server mounts all tool sub-servers at initialization
   - Lazy namespaces are initially disabled via `mcp.disable()`
   - Tools remain available for invocation based on their visibility tags

3. **Shutdown** (`lifespan` function cleanup):
   - Cancels unfinished in-memory queued/running background tasks
   - Calls `db_close_engine()` to release database connections

### Tool Discovery and Activation
The server implements a two-tier tool visibility system:

**Core Tools (Always Visible)**:
- `memory_store`, `memory_recall`, `memory_search`
- `decision_record`, `decision_search` 
- `task_search`, `task_update`
- `project_search`
- `tools_activate` (gateway to lazy namespaces)
- `tools_search` (discovery mechanism)

**Lazy Namespaces (Session-Activated)**:
- `memory`, `work`, `notes`, `audit`, `filesystem`, `background`, `graph`

Activation Flow:
1. Client calls `tools_search(query="...")` to find relevant tools
2. Client calls `tools_activate(namespace="<name>")` with Context
3. Server enables components matching `namespace:<name>` tag for that session
4. FastMCP automatically sends ToolListChangedNotification to update client tool list

### Request/Response Paths
All MCP tool invocations follow this pattern:
1. Client sends tool call request via HTTP/SSE/stdio
2. FastMCP routes to appropriate tool handler based on method name
3. Handler executes with automatic Context injection (when requested)
4. Handler accesses database via `get_conn()` from `src/mem-graph/db.py`
5. Handler performs Ladybug Cypher operations
6. Handler returns structured dict response serialized by FastMCP

### Background Task Flow
Ordinary calls to `audit_package`, `map_codebase`, `triage_violations`, and `orchestrate_codebase` are queued in an in-memory `TaskQueue` and return a task identifier immediately. Clients poll `get_task_status(task_id)` and may call `cancel_task(task_id)` while the task is queued or running.

The same tools also advertise FastMCP `task=True`, so SEP-1686-capable clients can run them as native FastMCP tasks instead of using the in-process queue.

### Dashboard Routes
The HTTP app now serves both MCP endpoints and a lightweight graph dashboard:
- `/dashboard` - dashboard HTML shell
- `/dashboard.js` - client logic
- `/dashboard.css` - dashboard styles
- `/dashboard/api/graph` - graph snapshot JSON
- `/dashboard/api/node/{node_id}` - node details JSON
- `/dashboard/api/search` - search JSON
- `/dashboard/api/styles` - node style metadata JSON
- `/health` - health endpoint
- `/mcp` - streamable MCP HTTP transport
- `/sse` - SSE transport

### Data Flow
```
Client Request 
    → FastMCP Routing 
    → Tool Handler (src/mem-graph/tools/*.py)
    → Database Connection (src/mem-graph/db.py:get_conn)
    → Ladybug Database Operations
    → Result Returned to Client
```

### State Management
The server maintains minimal internal state:
- Database connection singleton (managed in `src/mem_graph/db.py`)
- Tool visibility tags (managed via FastMCP's provider system)
- In-memory task queue state for long-running audit operations
- No general-purpose caching of graph or tool query results - normal reads still hit the database

### Error Handling
- Database initialization failures raise RuntimeError during startup
- Ollama connection failures prevent server start with clear error messages
- Individual tool handlers catch exceptions and return error dicts
- Ladybug transaction handling depends on individual operation semantics

### Logging and Observability
- Startup prints connection information to stderr
- Ollama pull progress printed to stderr
- No built-in structured logging - relies on stdout/stderr capture
- MCP protocol provides built-in request/response tracing capabilities

### Code References
- Main server logic: `src/mem_graph/server.py`
- Database initialization: `src/mem_graph/db.py`
- Schema definition: `schema/agent_memory_schema.cypher`
- Tool implementations: `src/mem_graph/tools/*.py`
