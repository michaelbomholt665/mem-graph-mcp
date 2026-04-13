# API Reference Documentation

## Purpose
This document provides comprehensive documentation of the public and internal APIs exposed by the Syntx Memory MCP Server. It covers endpoints, message formats, event types, and payload schemas for all MCP protocol interactions.

## Overview
The server implements the Model Context Protocol (MCP) using FastMCP framework, providing both HTTP and SSE transport mechanisms. All APIs follow JSON-RPC 2.0 format with MCP-specific extensions for tool discovery and invocation.

## Transport Protocols

### HTTP Transport
- **Base URL**: `http://127.0.0.1:9100` (configurable via `MCP_HOST`/`MCP_PORT`)
- **Endpoints**:
  - `/mcp` - Streamable HTTP for tool calls and responses
  - `/sse` - Server-Sent Events for real-time notifications

### SSE Transport
- **Endpoint**: `/sse`
- **Protocol**: Server-Sent Events with JSON-RPC 2.0 payloads
- **Use Case**: Real-time tool list updates and notifications

### Stdio Transport
- **Protocol**: Standard input/output streams
- **Use Case**: Local process communication
- **Configuration**: Set `MCP_TRANSPORT=stdio`

## Message Formats

### JSON-RPC 2.0 Structure
All MCP communications use JSON-RPC 2.0:

```json
{
  "jsonrpc": "2.0",
  "id": "request-123",
  "method": "tools/call",
  "params": {
    "name": "memory_store",
    "arguments": {
      "content": "User prefers TypeScript over JavaScript",
      "kind": "preference"
    }
  }
}
```

### MCP-Specific Extensions
MCP adds protocol-specific methods and notifications:

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/tools/list_changed",
  "params": {}
}
```

## Tool Discovery APIs

### tools_search
Search available tools by functionality or name.

**Method**: `tools/call`  
**Tool Name**: `tools_search`

**Parameters**:
```typescript
{
  query: string  // Search query for tool discovery
}
```

**Response**:
```typescript
{
  results: Array<{
    tool: string,        // Tool name
    purpose: string,     // Tool description
    namespace: string,   // Activation namespace
    score: number        // Relevance score
  }>,
  suggestion: string    // Usage guidance
}
```

**Example**:
```json
{
  "jsonrpc": "2.0",
  "id": "search-001",
  "method": "tools/call",
  "params": {
    "name": "tools_search",
    "arguments": {
      "query": "conversation storage"
    }
  }
}
```

### tools_activate
Activate lazy-loaded tool namespaces for the current session.

**Method**: `tools/call`  
**Tool Name**: `tools_activate`

**Parameters**:
```typescript
{
  namespace: string  // Namespace to activate
}
```

**Response**:
```typescript
{
  activated: string,  // Activated namespace
  status: string      // "ok" on success
}
```

**Error Response**:
```typescript
{
  error: string  // Error description
}
```

## Memory Management APIs

### memory_store
Store a memory item with semantic embedding.

**Method**: `tools/call`  
**Tool Name**: `memory_store`

**Parameters**:
```typescript
{
  content: string,     // Memory content
  kind: string,        // fact | preference | pattern | violation | architecture
  scope: string,       // global | project | backend | task
  project_id?: string  // Required if scope is project/backend/task
}
```

**Response**:
```typescript
{
  memory_id: string,   // UUID of created memory
  status: string       // "stored"
}
```

### memory_recall
Retrieve memories semantically similar to a query.

**Method**: `tools/call`  
**Tool Name**: `memory_recall`

**Parameters**:
```typescript
{
  query: string,       // Search query
  scope: string,       // global | project | backend | task
  project_id?: string, // Required for project/backend/task scope
  limit?: number       // Max results (default: 10)
}
```

**Response**:
```typescript
{
  memories: Array<{
    id: string,
    content: string,
    kind: string,
    scope: string,
    confidence: number,
    distance: number,
    created_at: string
  }>
}
```

## Conversation APIs

### conversation_start
Initialize a new conversation session.

**Method**: `tools/call`  
**Tool Name**: `conversation_start`

**Parameters**:
```typescript
{
  project_id: string,  // Project identifier
  agent_name: string,  // Agent name (e.g., "claude-opus")
  model: string        // Model identifier
}
```

**Response**:
```typescript
{
  conversation_id: string,  // UUID of conversation
  status: string           // "started"
}
```

### conversation_append
Add a message to an ongoing conversation.

**Method**: `tools/call`  
**Tool Name**: `conversation_append`

**Parameters**:
```typescript
{
  conversation_id: string,  // Conversation UUID
  role: string,             // user | assistant | system | tool
  content: string,          // Message content
  tool_name?: string        // Tool name if role is "tool"
}
```

**Response**:
```typescript
{
  message_id: string,  // UUID of message
  position: number     // Message position in conversation
}
```

### conversation_end
Complete a conversation and generate summary.

**Method**: `tools/call`  
**Tool Name**: `conversation_end`

**Parameters**:
```typescript
{
  conversation_id: string  // Conversation UUID
}
```

**Response**:
```typescript
{
  conversation_id: string,  // Conversation UUID
  summary: string,          // Generated summary
  message_count: number     // Total messages
}
```

## Task Management APIs

### task_create
Create a new task with optional embedding.

**Method**: `tools/call`  
**Tool Name**: `task_create`

**Parameters**:
```typescript
{
  project_id: string,    // Project identifier
  title: string,         // Task title
  description: string,   // Task description
  priority?: string,     // low | normal | high | critical
  backend_id?: string    // Backend identifier
}
```

**Response**:
```typescript
{
  task_id: string,  // UUID of created task
  status: string    // "created"
}
```

### task_update
Update task status, priority, or phase.

**Method**: `tools/call`  
**Tool Name**: `task_update`

**Parameters**:
```typescript
{
  task_id: string,      // Task UUID
  status?: string,      // open | in_progress | blocked | done | cancelled
  phase?: string,       // planning | red | green | refactor | audit
  priority?: string     // low | normal | high | critical
}
```

**Response**:
```typescript
{
  task_id: string,  // Task UUID
  status: string    // "updated"
}
```

## Project Management APIs

### project_create
Create a new project.

**Method**: `tools/call`  
**Tool Name**: `project_create`

**Parameters**:
```typescript
{
  name: string,          // Project name
  description: string,   // Project description
  repo_path?: string     // Repository path
}
```

**Response**:
```typescript
{
  project_id: string,  // UUID of created project
  status: string       // "created"
}
```

## Decision APIs

### decision_record
Record an architectural decision.

**Method**: `tools/call`  
**Tool Name**: `decision_record`

**Parameters**:
```typescript
{
  project_id: string,     // Project identifier
  title: string,          // Decision title
  rationale: string,      // Decision rationale
  alternatives?: string,  // Rejected alternatives
  impact?: string         // low | medium | high | critical
}
```

**Response**:
```typescript
{
  decision_id: string,  // UUID of decision
  status: string        // "recorded"
}
```

## Agent APIs

### audit_package
Run automated codebase audit using the Audit Agent.

**Method**: `tools/call`  
**Tool Name**: `audit_package`

**Parameters**:
```typescript
{
  package_path: string,        // Path to package directory
  guide_file_path: string,     // Path to coding guidelines file
  registry_file_path: string   // Path to smell registry file
}
```

**Response**:
```typescript
{
  status: string,        // "audit_completed"
  summary: string,       // Audit summary
  actions_taken: Array<string>  // List of actions performed
}
```

## Event Types and Notifications

### ToolListChangedNotification
Sent when tool availability changes due to namespace activation.

**Method**: `notifications/tools/list_changed`

**Payload**:
```typescript
{
  jsonrpc: "2.0",
  method: "notifications/tools/list_changed",
  params: {}
}
```

## Error Handling

### Standard Error Format
All tools return errors in a consistent format:

```typescript
{
  error: string  // Human-readable error message
}
```

### Common Error Codes
- `Unknown namespace`: Invalid namespace in `tools_activate`
- `Database connection failed`: Ladybug DB unavailable
- `Embedding generation failed`: Ollama service unavailable
- `Validation error`: Invalid parameter values
- `Not found`: Referenced entity doesn't exist

## Authentication and Authorization

### Current State
The MCP server currently implements no authentication or authorization mechanisms. All clients have full access to all tools and data.

### Future Considerations
- API key authentication
- Session-based access control
- Project-scoped permissions
- Role-based tool access

## Rate Limiting

### Current Implementation
No rate limiting is currently implemented.

### Future Considerations
- Request rate limits per client
- Concurrent session limits
- Resource usage quotas

## Payload Schemas

### UUID Format
All identifiers use UUIDv7 format:
```
0192a1b2-3c4d-5e6f-7g8h-9i0j1k2l3m4n
```

### Timestamp Format
All timestamps use ISO 8601 with timezone:
```
2024-01-15T10:30:00Z
```

### Embedding Vectors
Semantic embeddings are 1536-dimensional float arrays:
```typescript
embedding: number[1536]
```

## Code References
- Server endpoints: `src/mem-graph/server.py:248-249`
- Tool implementations: `src/mem-graph/tools/*.py`
- Message format handling: FastMCP framework
- Error handling patterns: All tool functions return `{"error": "..."}` on failure