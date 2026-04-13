# Glossary Documentation

## Purpose
This document defines terms and acronyms used across the Syntx Memory MCP Server documentation to ensure consistent terminology and understanding.

## Terms
### Agent
An autonomous software entity that interacts with the MCP server and tools to perform complex tasks. Agents encapsulate decision-making logic, state management, and workflow execution. Example: Audit Agent for codebase analysis.

### Backend
A language or service boundary within a project, used for organizing code components. Examples: Python backend, React frontend, database service.

### Conversation
A discrete session of interaction between an AI agent and the system, consisting of multiple messages with automatic summarization and embedding for semantic recall.

### Cypher
The query language used by Ladybug graph database for creating, reading, and manipulating graph data structures.

### Decision
An architectural or implementation choice recorded in the system with rationale, alternatives considered, and impact assessment. Decisions can be superseded by newer choices.

### Embedding
A numerical vector representation of text content used for semantic similarity search. Generated using Ollama models, typically 1536-dimensional float arrays.

### FastMCP
The Python framework implementing the Model Context Protocol, providing server infrastructure, tool mounting, and transport mechanisms.

### Graph Database
A database that uses graph structures with nodes, relationships, and properties to represent and store data. Ladybug is the specific graph database used.

### HNSW
Hierarchical Navigable Small World - an algorithm for approximate nearest neighbor search in high-dimensional spaces, used for vector similarity search.

### Ladybug
An embedded graph database written in Rust, used for storing the knowledge graph of projects, conversations, tasks, decisions, and other entities.

### MCP
Model Context Protocol - an open standard for AI model integration with external tools, defining the interface for tool discovery and invocation.

### Memory
Distilled, persistent facts extracted from conversations for cross-session recall. Memories have kinds (fact, preference, pattern), scopes (global, project, backend, task), and semantic embeddings.

### Message
An individual turn in a conversation, containing role (user/assistant/system/tool), content, and optional tool call information.

### Namespace
A logical grouping of related tools that can be activated together for session-based visibility. Examples: conversation, task, decision, audit.

### Node
A fundamental unit in the graph database representing entities like Project, Task, Decision, etc. Nodes have labels, properties, and relationships.

### Note
A free-form text entry for observations, findings, or reminders, with optional tagging and semantic search capabilities.

### Ollama
A local AI model server for running large language models and embedding models without external API dependencies.

### Project
A top-level isolation boundary for organizing work, containing backends, tasks, decisions, conversations, and other artifacts.

### Relationship
A typed connection between nodes in the graph database, representing associations like HAS_TASK, TASK_DECISION, etc.

### Scope
A filtering mechanism for memory and search operations, determining visibility boundaries: global (all projects), project (single project), backend (language/service), task (specific task).

### Semantic Search
Search based on meaning rather than exact keyword matching, using vector embeddings and similarity metrics to find relevant content.

### Session
A client connection context that maintains tool activation state and namespace visibility during an MCP interaction.

### Task
A unit of work tracked across agent sessions, with status, priority, blocking dependencies, and links to decisions and violations.

### Tool
A function exposed via MCP that performs specific operations, from simple data storage to complex agent invocations.

### UUIDv7
A version of Universally Unique Identifier that includes timestamp information for temporal ordering and uniqueness.

### Vector Index
A specialized index for efficient similarity search over high-dimensional vector embeddings using algorithms like HNSW.

### Violation
A recorded policy violation, code smell, or audit finding with lifecycle management (open, resolved, recurrence, graduated).

## Acronyms
### AI - Artificial Intelligence
Machine learning systems capable of performing tasks that typically require human intelligence.

### API - Application Programming Interface
A set of rules and protocols for accessing a software application or system.

### CRUD - Create, Read, Update, Delete
The four basic operations for persistent storage systems.

### CWE - Common Weakness Enumeration
A community-developed list of software and hardware weakness types.

### DB - Database
An organized collection of data stored and accessed electronically.

### DoS - Denial of Service
An attack that makes a server unavailable to legitimate users.

### GDPR - General Data Protection Regulation
European Union regulation on data protection and privacy.

### HNSW - Hierarchical Navigable Small World
Algorithm for efficient approximate nearest neighbor search.

### HTTP - Hypertext Transfer Protocol
Protocol for transferring data over the web.

### HTTPS - Hypertext Transfer Protocol Secure
Secure version of HTTP using TLS/SSL encryption.

### IDE - Integrated Development Environment
Software application for software development with code editing, debugging, and build tools.

### JSON - JavaScript Object Notation
Lightweight data interchange format.

### JSON-RPC - JSON Remote Procedure Call
Protocol for calling methods on remote systems using JSON.

### MCP - Model Context Protocol
Open standard for AI model integration with external tools.

### PII - Personally Identifiable Information
Information that can identify an individual person.

### RBAC - Role-Based Access Control
Security approach defining permissions based on user roles.

### REST - Representational State Transfer
Architectural style for web services.

### SDK - Software Development Kit
Set of tools for developing software applications.

### SSE - Server-Sent Events
Web standard for real-time communication from server to client.

### TLS - Transport Layer Security
Cryptographic protocol for secure communication.

### UUID - Universally Unique Identifier
Standard for generating unique identifiers.

## References
### Code References
- Term definitions derived from: `src/mem-graph/` implementations
- Acronym usage: Throughout documentation and code comments

### External References
- MCP Specification: https://modelcontextprotocol.io/
- UUID Standard: RFC 9562
- Cypher Query Language: Ladybug documentation
