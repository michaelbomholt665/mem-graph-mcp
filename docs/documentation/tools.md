# Tools Component Documentation

## Purpose
This document explains the Syntx Memory MCP Tools component - the collection of specialized functional modules that provide capabilities for memory storage, task management, conversation capture, decision recording, and more. Each tool is implemented as a FastMCP sub-server with specific responsibilities.

## Overview
Tools are organized in `src/mem_graph/tools/` as individual Python modules, each exposing a FastMCP instance (`mcp`) that gets mounted into the main server. Tools follow a consistent pattern:
- Database access via `db_get_connection()` from `src/mem_graph/db.py`
- Embedding generation via `embeddings_generate()` from `src/mem_graph/embeddings.py`
- UUID-based identification using `uuid.uuid4()`
- Timestamp handling with timezone-aware UTC datetimes

### Two-Tier Visibility System
As documented in server.md, tools are split into:
1. **Core Tools** (always visible): discovery, search, and common work-management functions
2. **Lazy Namespaces** (session-activated): specialized tool groups requiring explicit activation

Current lazy namespaces are `memory`, `work`, `notes`, `audit`, `filesystem`, `background`, and `graph`.

## Tool Categories

### Memory Tools (`src/mem-graph/tools/memory.py`)
Responsible for storing and retrieving distilled memories with semantic search capabilities.

**Key Tools:**
- `memory_store(content, kind, scope, project_id)` - Store a memory node with embedding
- `memory_recall(query, scope, project_id, limit)` - Semantic search with filtering
- `memory_search(query, limit)` - Cross-scope semantic search
- `memory_expire(memory_id)` - Soft-delete by setting expiration
- `memory_list(scope, project_id)` - Browse memories without ranking

**Data Flow:**
```
Store: content → embed() → Memory node → (optional) PROJECT_MEMORY link
Recall: query → embed() → QUERY_VECTOR_INDEX → filter → return memories
```

### Conversation Tools (`src/mem-graph/tools/conversation.py`)
Handles conversation lifecycle management and message storage with automatic summarization.

**Key Tools:**
- `conversation_start(project_id, agent_name, model)` - Initialize session
- `conversation_append(conversation_id, role, content, tool_name)` - Add message
- `conversation_end(conversation_id)` - Close session + generate Ollama summary
- `conversation_get(conversation_id)` - Retrieve full conversation

**Data Flow:**
```
Start: Create Conversation + Agent nodes + links
Append: 
  1. content → embed() → Message node
  2. Conversation →[CONVERSATION_MESSAGE{position}]→ Message
  3. (if not first) Previous Message →[NEXT_MESSAGE]→ Current Message
  4. Increment turn_count
End: 
  1. Fetch all messages in order
  2. Generate summary via Ollama
  3. Store summary + embedding on Conversation node
```

### Task Tools (`src/mem-graph/tools/tasks.py`)
Manages units of work tracked across sessions with blocking dependencies and links to decisions/violations.

**Key Tools:**
- `task_create(project_id, title, description, priority, backend_id)` - Create task
- `task_update(task_id, status, phase, priority)` - Update task attributes
- `task_get(task_id)` - Retrieve task with linked decisions/violations
- `task_search(query, project_id, limit)` - Semantic search over tasks
- `task_link_decision(task_id, decision_id)` - Create TASK_DECISION link
- `task_link_violation(task_id, violation_id)` - Create TASK_VIOLATION link
- `task_block(blocked_id, blocker_id, reason)` - Create blocking dependency

**Data Flow:**
```
Create: 
  title+description → embed() → Task node
  Project →[HAS_TASK]→ Task
  (optional) Backend →[BACKEND_TASK]→ Task

Links:
  Task →[TASK_DECISION]→ Decision
  Task →[TASK_VIOLATION]→ Violation
  Blocker Task →[TASK_BLOCKS{reason}]→ Blocked Task
```

### Decision Tools (`src/mem-graph/tools/decisions.py`)
Records architectural decisions and tracks their lineage through supersession relationships.

**Key Tools:**
- `decision_record(project_id, title, rationale, alternatives, impact)` - Record decision
- `decision_supersede(old_id, new_id, reason)` - Mark decision as superseded
- `decision_get(decision_id)` - Retrieve decision with full lineage
- `decision_search(query, project_id, limit)` - Semantic search over decisions

**Data Flow:**
```
Record: title+rationale(+alternatives) → embed() → Decision node
        Project →[HAS_DECISION]→ Decision

Supersede:
  Old Decision.status = 'superseded'
  New Decision →[SUPERSEDES{reason}]→ Old Decision
```

### Project Tools (`src/mem-graph/tools/projects.py`)
Manages top-level isolation boundaries for organizing work.

**Key Tools:**
- `project_create(name, description, repo_path)` - Create project
- `project_get(project_id)` - Retrieve project details
- `project_list()` - List all projects
- `project_search(query, limit)` - Semantic search over projects

### Note Tools (`src/mem-graph/tools/notes.py`)
Handles free-form observations, findings, and reminders with tagging capabilities.

**Key Tools:**
- `note_create(project_id, kind, title, body, tags)` - Create note
- `note_search(query, limit)` - Semantic search over notes
- `note_list()` - List notes without ranking

### Violation Tools (`src/mem-graph/tools/violations.py`)
Tracks policy violations, smells, and audit findings with lifecycle management.

**Key Tools:**
- `violation_record(...)` - Record new violation
- `violation_resolve(violation_id)` - Mark violation as resolved
- `violation_recur(violation_id)` - Mark as recurring
- `violation_search(query, limit)` - Semantic search over violations
- `violation_list()` - List violations

### Audit Tools (`src/mem_graph/tools/agents/`)
Interfaces with the autonomous Audit Agent for package codebase audits.

**Key Tools:**
- `audit_package(package_path, project_id, ...)` - Queue or run an automated audit
- `map_codebase(package_path, known_features, ...)` - Queue or run codebase cartography
- `triage_violations(project_id, raw_findings)` - Queue or run violation triage
- `orchestrate_codebase(package_path, project_id, subagent_name, ...)` - Queue or run batched analysis

For ordinary MCP callers these heavy tools enqueue in-memory work and return a `task_id` immediately. For SEP-1686-aware clients the same tools also support FastMCP `task=True` execution.

### Background Tools (`src/mem_graph/tools/background/task_status.py`)
Provides a queue-agnostic polling surface for long-running audit operations.

**Key Tools:**
- `get_task_status(task_id)` - Retrieve normalized queue state, progress, and terminal result data
- `cancel_task(task_id)` - Cancel queued work and request cancellation of running work

Background task state is in-memory only and is cleared on server shutdown.

### Graph Tools (`src/mem_graph/tools/graph/graph_queries.py`)
Backs the lightweight dashboard and graph-aware MCP clients.

**Key Tools:**
- `get_graph_snapshot(project_id, node_types, depth, max_nodes)` - Return a bounded graph view for visualization
- `get_node_details(node_id)` - Return a node plus neighboring relationships
- `search_graph(query, project_id, node_types, limit)` - Perform bounded text search across visible graph nodes

**Stable Resources:**
- `graph://snapshot`
- `graph://nodes/{node_id}`
- `graph://styles`

## Tool Discovery Mechanisms

### Built-in Search
Each lazy namespace includes search tools:
- `*_search(query, limit)` - Semantic search over that tool's domain
- `*_get(id)` - Direct retrieval by ID

### Cross-Namespace Discovery
The `tools_search(query)` tool in server.py provides unified discovery:
1. Lists all available tools (including disabled ones)
2. Filters out core discovery tools (`tools_activate`, `tools_search`)
3. Scores results by keyword matches in tool name/description
4. Extracts namespace from tool tags (using `namespace:<name>` pattern)
5. Returns top 10 results with activation instructions

## Tool Invocation Patterns

### Standard Pattern
All tools follow this invocation pattern:
```python
@mcp.tool()
async def tool_name(
    param1: Annotated[type, Field(description="...")],
    param2: Annotated[type, Field(description="..."), default="value"]
) -> dict:
    # Implementation
    return {"result": "value"}
```

### Context Access
Tools requiring FastMCP context declare it:
```python
async def tool_name(
    param: Annotated[type, Field(description="...")],
    ctx: Context
) -> dict:
    # Use ctx for session-specific operations
    await ctx.enable_components(...) 
    return {"result": "value"}
```

### Tags for Visibility
Lazy namespace tools use tags for session-based visibility:
```python
@mcp.tool(tags={"namespace:background"})
async def get_task_status(...) -> dict:
  # Only visible after tools_activate(namespace="background")
    return {"result": "value"}
```

### Background Task Pattern
Heavy tools follow a shared invocation pattern:
1. Ordinary tool call → queue work in the in-memory `TaskQueue` and return a `task_id`
2. Poll `get_task_status(task_id)` until the task reaches a terminal state
3. Optionally call `cancel_task(task_id)` while the task is queued or running
4. SEP-1686 clients may instead execute the same tool in FastMCP task mode (`task=True`)

## Orchestration Examples

### Typical Conversation Flow
1. Agent calls `tools_activate(namespace="conversation")`
2. Agent calls `conversation_start(project_id, agent_name, model)` → gets conversation_id
3. For each turn:
   - Agent calls `conversation_append(conversation_id, role, content)`
4. Agent calls `conversation_end(conversation_id)` → gets summary

### Task with Decision Linking
1. Agent calls `task_create(project_id, title, description)` → gets task_id
2. Agent calls `decision_record(project_id, title, rationale)` → gets decision_id
3. Agent calls `task_link_decision(task_id, decision_id)`

### Semantic Recall Workflow
1. Agent formulates natural language query
2. Agent calls `memory_recall(query, scope="project", project_id="xyz", limit=5)`
3. Receives ranked memories with distance scores
4. Uses results to inform current work

## Error Handling Conventions
- Tools return dict objects with either success data or error information
- Error format: `{"error": "descriptive message"}`
- Success format varies by tool but typically includes IDs or requested data
- Database connection failures raise exceptions that propagate upward
- Validation failures return error dicts (e.g., invalid namespace in tools_activate)

## Dependencies
- Database layer: `src/mem_graph/db.py`
- Embedding service: `src/mem_graph/embeddings.py`
- External services: Ollama (for embeddings and summarization)
- Ladybug graph database (for data storage)
