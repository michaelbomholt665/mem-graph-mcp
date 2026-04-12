# Syntx Memory MCP Server

Syntx Memory is an agent memory store for Syntx implemented as an MCP (Model Context Protocol) server. It leverages the FastMCP framework to provide robust capability for capturing and inter-linking conversations, tasks, decisions, notes, and audit violations, enabling semantic recall across AI assistant sessions.

## Features & Capabilities

The server provides a suite of MCP tools categorized by domain:

### 1. Memory Management
Tools to capture arbitrary information and retrieve it semantically across sessions.
- **`memory_store`**: Store a specific memory or information snippet dynamically.
- **`memory_recall`**: Recall memories by querying specific concepts or topics.
- **`memory_search`**: Perform semantic search over all stored memories.
- **`memory_list`**: List stored memories.
- **`memory_expire`**: Expire or remove a memory when it's no longer relevant.

### 2. Conversational Tracking
End-to-end conversation transcript storage and summarization.
- **`conversation_start`**: Initiate the tracking of a new conversation session.
- **`conversation_append`**: Append transcript data or messages to the ongoing conversation.
- **`conversation_end`**: End a conversation and automatically generate summaries.
- **`conversation_get`**: Retrieve the details and transcript of a specified conversation.

### 3. Project Management
Tools to define and track larger overarching projects.
- **`project_create`**: Initialize a new project.
- **`project_get`**: Retrieve a project by its identifier.
- **`project_list`**: List active and inactive projects.
- **`project_search`**: Search through the project repository.

### 4. Task Tracking
Fine-grained task definition, updates, and linking.
- **`task_create`**: Create a new task within a project.
- **`task_update`**: Update an existing task's status, assignee, or details.
- **`task_get`**: Fetch the current state of a task.
- **`task_search`**: Look up tasks matching specific criteria.
- **`task_link_decision`**: Link a task to an architectural or structural decision.
- **`task_link_violation`**: Link a task to an identified rule or audit violation.
- **`task_block`**: Mark a task as blocked and optionally record the reason.

### 5. Architectural Decisions
Formal tracking of decisions that impact the codebase or project trajectory.
- **`decision_record`**: Record a new decision, rationale, and context.
- **`decision_supersede`**: Mark an older decision as superseded by a newer one.
- **`decision_get`**: Retrieve the details of a specific decision.
- **`decision_search`**: Search historical decisions.

### 6. Notes
Ad-hoc text and documentation storage.
- **`note_create`**: Create a freeform note.
- **`note_search`**: Search existing notes.
- **`note_list`**: List all notes.

### 7. Violations & Auditing
Tools to identify, record, and resolve rule violations or bad practices.
- **`violation_record`**: Record an observed code, architecture, or workflow violation.
- **`violation_resolve`**: Mark a documented violation as resolved.
- **`violation_recur`**: Log when a resolved violation recurs.
- **`violation_search`**: Search through the database of recorded violations.
- **`violation_list`**: List accumulated violations to track frequency or severity.

## Architecture

The MCP Server is built using:
- **FastMCP**: Provides the foundation for routing, lifecycle, and multiple transport supports (stdio, chunked streamable HTTP, and SSE).
- **Ladybug DB**: Serves as the underlying robust graph database where all these entities are interlinked and serialized to facilitate semantic querying across nodes.
- **Ollama**: Generates local, dense semantic embeddings of textual data enabling nearest-neighbor concept searches natively across your tracked interactions and states.
