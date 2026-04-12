# Data Models Documentation

## Purpose
This document explains the core data models, schemas, and data contracts used across the Syntx Memory MCP Server. It covers the graph database structure, node and relationship definitions, embedding specifications, and provides example payloads for key operations.

## Overview
The system uses a Ladybug graph database to store interconnected entities representing agent memory, conversations, tasks, decisions, and violations. All embeddable nodes use 1536-dimensional float vectors for semantic similarity search. Data is structured around projects as top-level isolation boundaries with hierarchical relationships.

### Core Concepts
- **UUIDv7 Primary Keys**: All entities use UUIDv7 strings for temporal ordering and uniqueness
- **Embedding Dimensions**: 1536-dimensional vectors for semantic search (OpenAI text-embedding-3-small compatible)
- **Timestamp Handling**: UTC timezone-aware timestamps with creation/update tracking
- **Graph Relationships**: Typed relationships connecting entities with optional properties

## Node Schemas

### Agent Node
Represents an AI agent instance participating in conversations and authoring content.

```cypher
CREATE NODE TABLE IF NOT EXISTS Agent (
    id          STRING PRIMARY KEY,   -- UUIDv7
    name        STRING,               -- e.g. "claude-opus-4-6", "codex-cli"
    role        STRING,               -- planner | coder | auditor | reviewer
    model       STRING,               -- raw model string
    created_at  TIMESTAMP DEFAULT current_timestamp()
);
```

**Example Payload:**
```json
{
  "id": "0192a1b2-3c4d-5e6f-7g8h-9i0j1k2l3m4n",
  "name": "claude-3-5-sonnet",
  "role": "coder",
  "model": "claude-3-5-sonnet-20241022",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Project Node
Top-level isolation boundary for organizing work across multiple backends and sessions.

```cypher
CREATE NODE TABLE IF NOT EXISTS Project (
    id          STRING PRIMARY KEY,
    name        STRING,
    description STRING,
    status      STRING DEFAULT 'active',  -- active | paused | archived
    repo_path   STRING,
    embedding   FLOAT[1536],
    created_at  TIMESTAMP DEFAULT current_timestamp(),
    updated_at  TIMESTAMP DEFAULT current_timestamp()
);
```

**Example Payload:**
```json
{
  "id": "0192a1b2-3c4d-5e6f-7g8h-9i0j1k2l3m4n",
  "name": "e-commerce-platform",
  "description": "Microservices-based e-commerce platform with React frontend",
  "status": "active",
  "repo_path": "/home/user/projects/ecommerce",
  "embedding": [0.123, 0.456, ...],  // 1536 floats
  "created_at": "2024-01-15T09:00:00Z",
  "updated_at": "2024-01-20T14:30:00Z"
}
```

### Backend Node
Language/service boundary within a project for code organization.

```cypher
CREATE NODE TABLE IF NOT EXISTS Backend (
    id          STRING PRIMARY KEY,
    name        STRING,
    language    STRING,               -- go | python | typescript | rust | …
    root_path   STRING,
    description STRING,
    embedding   FLOAT[1536],
    created_at  TIMESTAMP DEFAULT current_timestamp()
);
```

### Task Node
Unit of work tracked across agent sessions with status and priority management.

```cypher
CREATE NODE TABLE IF NOT EXISTS Task (
    id           STRING PRIMARY KEY,
    title        STRING,
    description  STRING,
    status       STRING DEFAULT 'open',   -- open | in_progress | blocked | done | cancelled
    priority     STRING DEFAULT 'normal', -- low | normal | high | critical
    audit_id     STRING,                  -- e.g. "002A" — matches violation lifecycle IDs
    phase        STRING,                  -- planning | red | green | refactor | audit
    embedding    FLOAT[1536],
    created_at   TIMESTAMP DEFAULT current_timestamp(),
    updated_at   TIMESTAMP DEFAULT current_timestamp(),
    completed_at TIMESTAMP
);
```

**Example Payload:**
```json
{
  "id": "0192a1b2-3c4d-5e6f-7g8h-9i0j1k2l3m4n",
  "title": "Implement user authentication service",
  "description": "Create JWT-based authentication with role-based access control",
  "status": "in_progress",
  "priority": "high",
  "audit_id": "AUTH-001",
  "phase": "green",
  "embedding": [0.234, 0.567, ...],
  "created_at": "2024-01-15T11:00:00Z",
  "updated_at": "2024-01-16T09:30:00Z",
  "completed_at": null
}
```

### Decision Node
Architectural or implementation choices with rationale and impact tracking.

```cypher
CREATE NODE TABLE IF NOT EXISTS Decision (
    id           STRING PRIMARY KEY,
    title        STRING,
    rationale    STRING,
    alternatives STRING,              -- rejected options, free text
    status       STRING DEFAULT 'active',  -- active | superseded | reverted
    impact       STRING DEFAULT 'low',     -- low | medium | high | critical
    embedding    FLOAT[1536],
    created_at   TIMESTAMP DEFAULT current_timestamp()
);
```

### Violation Node
Policy violations, code smells, or audit findings with lifecycle management.

```cypher
CREATE NODE TABLE IF NOT EXISTS Violation (
    id          STRING PRIMARY KEY,
    audit_id    STRING,               -- e.g. "002A"
    rule        STRING,               -- CWE-252, SonarQube:S2093, custom:no-todo
    severity    STRING DEFAULT 'info', -- info | minor | major | critical | blocker
    file_path   STRING,
    line_start  INT64,
    line_end    INT64,
    description STRING,
    status      STRING DEFAULT 'open', -- open | recurrence | resolved | graduated
    embedding   FLOAT[1536],
    detected_at TIMESTAMP DEFAULT current_timestamp(),
    resolved_at TIMESTAMP
);
```

**Example Payload:**
```json
{
  "id": "0192a1b2-3c4d-5e6f-7g8h-9i0j1k2l3m4n",
  "audit_id": "SEC-001",
  "rule": "CWE-79",
  "severity": "major",
  "file_path": "src/auth/login.py",
  "line_start": 45,
  "line_end": 47,
  "description": "Potential XSS vulnerability in user input sanitization",
  "status": "open",
  "embedding": [0.345, 0.678, ...],
  "detected_at": "2024-01-15T12:00:00Z",
  "resolved_at": null
}
```

### Conversation Node
Discrete agent session with automatic summarization and turn tracking.

```cypher
CREATE NODE TABLE IF NOT EXISTS Conversation (
    id          STRING PRIMARY KEY,
    title       STRING,
    summary     STRING,
    model       STRING,
    turn_count  INT64 DEFAULT 0,
    embedding   FLOAT[1536],
    started_at  TIMESTAMP DEFAULT current_timestamp(),
    ended_at    TIMESTAMP
);
```

### Message Node
Individual turn within a conversation with role and content tracking.

```cypher
CREATE NODE TABLE IF NOT EXISTS Message (
    id          STRING PRIMARY KEY,
    role        STRING,               -- user | assistant | system | tool
    content     STRING,
    tool_name   STRING,               -- populated when role=tool
    token_count INT64,
    embedding   FLOAT[1536],
    created_at  TIMESTAMP DEFAULT current_timestamp()
);
```

### Memory Node
Distilled, persistent facts extracted from conversations for cross-session recall.

```cypher
CREATE NODE TABLE IF NOT EXISTS Memory (
    id         STRING PRIMARY KEY,
    kind       STRING DEFAULT 'fact',  -- fact | preference | pattern | violation | architecture
    scope      STRING DEFAULT 'global', -- global | project | backend | task
    content    STRING,
    confidence FLOAT DEFAULT 1.0,
    embedding  FLOAT[1536],
    created_at TIMESTAMP DEFAULT current_timestamp(),
    updated_at TIMESTAMP DEFAULT current_timestamp(),
    expires_at TIMESTAMP              -- NULL = never expires
);
```

**Example Payload:**
```json
{
  "id": "0192a1b2-3c4d-5e6f-7g8h-9i0j1k2l3m4n",
  "kind": "preference",
  "scope": "project",
  "content": "User prefers async/await patterns over Promises for API calls",
  "confidence": 0.85,
  "embedding": [0.456, 0.789, ...],
  "created_at": "2024-01-15T13:00:00Z",
  "updated_at": "2024-01-15T13:00:00Z",
  "expires_at": null
}
```

### Note Node
Free-form observations, findings, or reminders with tagging support.

```cypher
CREATE NODE TABLE IF NOT EXISTS Note (
    id         STRING PRIMARY KEY,
    kind       STRING DEFAULT 'general',  -- general | finding | warning | lesson | audit
    title      STRING,
    body       STRING,
    tags       STRING[],                  -- arbitrary tag list
    embedding  FLOAT[1536],
    created_at TIMESTAMP DEFAULT current_timestamp()
);
```

## Relationship Schemas

### Containment Relationships
```cypher
CREATE REL TABLE IF NOT EXISTS HAS_BACKEND   (FROM Project  TO Backend,      assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_TASK      (FROM Project  TO Task,          assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_DECISION  (FROM Project  TO Decision,      assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_NOTE      (FROM Project  TO Note,          assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_VIOLATION (FROM Project  TO Violation,     assigned_at TIMESTAMP DEFAULT current_timestamp());
```

### Task Relationships
```cypher
CREATE REL TABLE IF NOT EXISTS TASK_BLOCKS    (FROM Task TO Task, reason STRING);
CREATE REL TABLE IF NOT EXISTS TASK_SPAWNS    (FROM Task TO Task, reason STRING);
CREATE REL TABLE IF NOT EXISTS TASK_DECISION  (FROM Task TO Decision);
CREATE REL TABLE IF NOT EXISTS TASK_VIOLATION (FROM Task TO Violation);
CREATE REL TABLE IF NOT EXISTS TASK_NOTE      (FROM Task TO Note);
```

### Conversation Chain
```cypher
CREATE REL TABLE IF NOT EXISTS PROJECT_CONVERSATION (FROM Project      TO Conversation);
CREATE REL TABLE IF NOT EXISTS AGENT_CONVERSATION   (FROM Agent        TO Conversation);
CREATE REL TABLE IF NOT EXISTS NEXT_MESSAGE         (FROM Message      TO Message,      turn_index INT64);
CREATE REL TABLE IF NOT EXISTS CONVERSATION_MESSAGE (FROM Conversation TO Message,      position   INT64);
```

### Memory Linkage
```cypher
CREATE REL TABLE IF NOT EXISTS MEMORY_SOURCE   (FROM Memory TO Conversation, extracted_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS PROJECT_MEMORY  (FROM Project  TO Memory);
CREATE REL TABLE IF NOT EXISTS BACKEND_MEMORY  (FROM Backend  TO Memory);
CREATE REL TABLE IF NOT EXISTS TASK_MEMORY     (FROM Task     TO Memory);
```

## Vector Indexes

The system uses HNSW vector indexes for efficient semantic similarity search:

```cypher
CALL CREATE_VECTOR_INDEX('Project',     'idx_project_emb',    'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Backend',     'idx_backend_emb',    'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Task',        'idx_task_emb',       'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Decision',    'idx_decision_emb',   'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Note',        'idx_note_emb',       'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Violation',   'idx_violation_emb',  'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Conversation','idx_conv_emb',       'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Message',     'idx_message_emb',    'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Memory',      'idx_memory_emb',     'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('CodeSymbol',  'idx_symbol_emb',     'embedding',  metric := 'cosine');
```

## Data Validation Rules

### Embedding Constraints
- All embedding vectors must be exactly 1536 floats
- Embeddings are generated using Ollama with `nomic-embed-text` model
- Cosine similarity metric used for all vector comparisons

### Temporal Ordering
- `created_at` timestamps must be set on creation and never modified
- `updated_at` timestamps updated on any modification
- UUIDv7 ensures temporal ordering of IDs across distributed systems

### Status Transitions
- **Task Status**: `open` → `in_progress` → `done` | `cancelled` | `blocked`
- **Violation Status**: `open` → `resolved` | `recurrence` | `graduated`
- **Decision Status**: `active` → `superseded` | `reverted`

## Example Query Patterns

### Semantic Memory Recall
```cypher
CALL QUERY_VECTOR_INDEX('Memory', 'idx_memory_emb', $query_vector, 10)
WITH node AS m, distance
WHERE m.scope = $scope AND (m.expires_at IS NULL OR m.expires_at > current_timestamp())
RETURN m.content, m.kind, m.confidence, distance
ORDER BY distance
LIMIT 5;
```

### Project Task Hierarchy
```cypher
MATCH (p:Project {id: $project_id})-[:HAS_TASK]->(t:Task)
OPTIONAL MATCH (t)-[:TASK_BLOCKS]->(blocked:Task)
OPTIONAL MATCH (t)-[:TASK_DECISION]->(d:Decision)
RETURN t, collect(blocked) as blocking, collect(d) as decisions;
```

### Conversation Replay
```cypher
MATCH (c:Conversation {id: $conversation_id})-[:CONVERSATION_MESSAGE]->(m:Message)
RETURN m.role, m.content, m.created_at
ORDER BY m.created_at;
```

## Migration and Schema Evolution

### Schema Versioning
- Schema changes tracked in `schema/agent_memory_schema.cypher`
- Version comments indicate breaking changes
- Indexes recreated when embedding dimensions change

### Data Migration Patterns
- UUIDv7 adoption for new entities
- Embedding regeneration required for model changes
- Relationship preservation during node updates

## References to Code
- Schema definition: `schema/agent_memory_schema.cypher`
- Database initialization: `src/syntx_mcp/db.py:init_db()`
- Embedding generation: `src/syntx_mcp/embeddings.py:embed()`
- Node creation patterns: All tool implementations in `src/syntx_mcp/tools/`