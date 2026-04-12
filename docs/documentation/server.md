# Server Component Documentation

## Purpose
This document explains the Syntx Memory MCP Server component - the foundation that provides the Model Context Protocol (MCP) server interface, handles tool discovery, manages lazy namespace activation, and orchestrates HTTP/SSE transport mechanisms.

## Overview
The server is implemented in `src/syntx_mcp/server.py` and serves as the entry point for all MCP interactions. It uses the FastMCP framework to provide a standardized interface for tools and agents while implementing custom logic for lazy tool loading and session-based namespace activation.

### Responsibilities
- Initialize and shutdown database connections via lifespan management
- Mount all tool sub-servers as namespaced components
- Provide tool discovery mechanisms (`tools_search`, `tools_activate`)
- Handle HTTP and SSE transport protocols
- Manage component visibility through tag-based enabling/disabling
- Ollama model probing and management during startup

## Architecture Details

### Server Lifecycle
The server uses FastMCP's lifespan context manager to handle initialization and cleanup:

1. **Startup** (`lifespan` function):
   - Calls `init_db()` from `src/syntx_mcp/db.py` to initialize Ladybug database
   - Installs and loads vector/fts extensions
   - Runs schema DDL from `schema/agent_memory_schema.cypher`
   - Creates vector indexes for all embeddable node types
   - Probes Ollama availability and pulls required embedding model if missing

2. **Runtime**:
   - Server mounts all tool sub-servers at initialization
   - Lazy namespaces are initially disabled via `mcp.disable()`
   - Tools remain available for invocation based on their visibility tags

3. **Shutdown** (`lifespan` function cleanup):
   - Calls `close_db()` to release database connections

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
- `conversation`, `decision`, `task`, `project`, `memory`, `note`, `violation`, `audit`

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
4. Handler accesses database via `get_conn()` from `src/syntx_mcp/db.py`
5. Handler performs Ladybug Cypher operations
6. Handler returns structured dict response serialized by FastMCP

### Data Flow
```
Client Request 
    → FastMCP Routing 
    → Tool Handler (src/syntx_mcp/tools/*.py)
    → Database Connection (src/syntx_mcp/db.py:get_conn)
    → Ladybug Database Operations
    → Result Returned to Client
```

### State Management
The server maintains minimal internal state:
- Database connection singleton (managed in `src/syntx_mcp/db.py`)
- Tool visibility tags (managed via FastMCP's provider system)
- No in-memory caching of tool results - all queries hit database

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
- Main server logic: `src/syntx_mcp/server.py`
- Database initialization: `src/syntx_mcp/db.py`
- Schema definition: `schema/agent_memory_schema.cypher`
- Tool implementations: `src/syntx_mcp/tools/*.py`
