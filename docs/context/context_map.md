## Context Map

This document enumerates files in src/ and lists their primary functions/classes with concise descriptions to help planning changes.

### Files & Key Functions

#### [src/syntx_mcp/__init__.py](src/syntx_mcp/__init__.py#L1)
- Purpose: Package initialization (minimal module header).

#### [src/syntx_mcp/db.py](src/syntx_mcp/db.py#L1)
- Purpose: Ladybug DB connection, schema bootstrap, and Ollama probe.
- Key functions:
	- `get_conn()` — [src/syntx_mcp/db.py](src/syntx_mcp/db.py#L41)
	- `init_db()` — [src/syntx_mcp/db.py](src/syntx_mcp/db.py#L48)
	- `close_db()` — [src/syntx_mcp/db.py](src/syntx_mcp/db.py#L61)
	- `_probe_ollama()` — [src/syntx_mcp/db.py](src/syntx_mcp/db.py#L75)
	- `_bootstrap(conn)` — [src/syntx_mcp/db.py](src/syntx_mcp/db.py#L93)
	- `_run_schema(conn)` — [src/syntx_mcp/db.py](src/syntx_mcp/db.py#L105)
	- `_ensure_vector_indexes(conn)` — [src/syntx_mcp/db.py](src/syntx_mcp/db.py#L147)

#### [src/syntx_mcp/embeddings.py](src/syntx_mcp/embeddings.py#L1)
- Purpose: Async-safe embedding helper wrapping Ollama.
- Key functions:
	- `embed(text: str)` — [src/syntx_mcp/embeddings.py](src/syntx_mcp/embeddings.py#L29)
	- `embed_dim()` — [src/syntx_mcp/embeddings.py](src/syntx_mcp/embeddings.py#L35)
	- `_embed_sync(text: str)` — [src/syntx_mcp/embeddings.py](src/syntx_mcp/embeddings.py#L45)

#### [src/syntx_mcp/server.py](src/syntx_mcp/server.py#L1)
- Purpose: FastMCP app definition, lifecycle, and gateway tools.
- Key items and functions:
	- `mcp` — FastMCP application instance (see file).
	- `lifespan(server)` — [src/syntx_mcp/server.py](src/syntx_mcp/server.py#L60)
	- `tools_search(query)` — [src/syntx_mcp/server.py](src/syntx_mcp/server.py#L97)
	- `tools_activate(namespace, ctx)` — [src/syntx_mcp/server.py](src/syntx_mcp/server.py#L190)
	- `run()` — [src/syntx_mcp/server.py](src/syntx_mcp/server.py#L238)
	- `combined_lifespan(app_instance)` — [src/syntx_mcp/server.py](src/syntx_mcp/server.py#L252)
	- `serve()` — [src/syntx_mcp/server.py](src/syntx_mcp/server.py#L262)

#### [src/syntx_mcp/agents/__init__.py](src/syntx_mcp/agents/__init__.py#L1)
- Purpose: Re-export `audit_agent`.

#### [src/syntx_mcp/agents/audit_agent.py](src/syntx_mcp/agents/audit_agent.py#L1)
- Purpose: Defines the Audit Agent, its input/output types, and helper tools used during audits.
- Key symbols and tools:
	- `AuditOutput` — [src/syntx_mcp/agents/audit_agent.py](src/syntx_mcp/agents/audit_agent.py#L7)
	- `AuditDependencies` — [src/syntx_mcp/agents/audit_agent.py](src/syntx_mcp/agents/audit_agent.py#L12)
	- `audit_agent` — Agent instance defined in-file.
	- `add_context_prompt(ctx)` — [src/syntx_mcp/agents/audit_agent.py](src/syntx_mcp/agents/audit_agent.py#L25)
	- Agent tools: `list_package_files()` — [src/syntx_mcp/agents/audit_agent.py](src/syntx_mcp/agents/audit_agent.py#L70), `read_file()` — [src/syntx_mcp/agents/audit_agent.py](src/syntx_mcp/agents/audit_agent.py#L77), `update_guide()` — [src/syntx_mcp/agents/audit_agent.py](src/syntx_mcp/agents/audit_agent.py#L88), `update_registry()` — [src/syntx_mcp/agents/audit_agent.py](src/syntx_mcp/agents/audit_agent.py#L98)

#### [src/syntx_mcp/tools/__init__.py](src/syntx_mcp/tools/__init__.py#L1)
- Purpose: Package header for tools (no runtime functions).

#### [src/syntx_mcp/tools/audit.py](src/syntx_mcp/tools/audit.py#L1)
- Purpose: MCP tool wrapper that invokes the `audit_agent` to run package audits.
- Key function:
	- `audit_package(...)` — [src/syntx_mcp/tools/audit.py](src/syntx_mcp/tools/audit.py#L14)

#### [src/syntx_mcp/tools/conversation.py](src/syntx_mcp/tools/conversation.py#L1)
- Purpose: Conversation capture, storage, summarisation, and retrieval.
- Helpers:
	- `_now()` — [src/syntx_mcp/tools/conversation.py](src/syntx_mcp/tools/conversation.py#L33)
	- `_new_id()` — [src/syntx_mcp/tools/conversation.py](src/syntx_mcp/tools/conversation.py#L37)
- Tools:
	- `conversation_start(...)` — [src/syntx_mcp/tools/conversation.py](src/syntx_mcp/tools/conversation.py#L47)
	- `conversation_append(...)` — [src/syntx_mcp/tools/conversation.py](src/syntx_mcp/tools/conversation.py#L106)
	- `conversation_end(...)` — [src/syntx_mcp/tools/conversation.py](src/syntx_mcp/tools/conversation.py#L195)
	- `conversation_get(...)` — [src/syntx_mcp/tools/conversation.py](src/syntx_mcp/tools/conversation.py#L251)
	- `_generate_summary(transcript)` — [src/syntx_mcp/tools/conversation.py](src/syntx_mcp/tools/conversation.py#L309)

#### [src/syntx_mcp/tools/decisions.py](src/syntx_mcp/tools/decisions.py#L1)
- Purpose: Record and query architectural decisions and lineage.
- Helpers:
	- `_now()` — [src/syntx_mcp/tools/decisions.py](src/syntx_mcp/tools/decisions.py#L20)
	- `_new_id()` — [src/syntx_mcp/tools/decisions.py](src/syntx_mcp/tools/decisions.py#L24)
- Tools:
	- `decision_record(...)` — [src/syntx_mcp/tools/decisions.py](src/syntx_mcp/tools/decisions.py#L29)
	- `decision_supersede(...)` — [src/syntx_mcp/tools/decisions.py](src/syntx_mcp/tools/decisions.py#L91)
	- `decision_get(...)` — [src/syntx_mcp/tools/decisions.py](src/syntx_mcp/tools/decisions.py#L127)
	- `decision_search(...)` — [src/syntx_mcp/tools/decisions.py](src/syntx_mcp/tools/decisions.py#L186)

#### [src/syntx_mcp/tools/memory.py](src/syntx_mcp/tools/memory.py#L1)
- Purpose: Store distilled memories and provide semantic recall/search.
- Helpers:
	- `_now()` — [src/syntx_mcp/tools/memory.py](src/syntx_mcp/tools/memory.py#L23)
	- `_new_id()` — [src/syntx_mcp/tools/memory.py](src/syntx_mcp/tools/memory.py#L27)
- Tools:
	- `memory_store(...)` — [src/syntx_mcp/tools/memory.py](src/syntx_mcp/tools/memory.py#L32)
	- `memory_recall(...)` — [src/syntx_mcp/tools/memory.py](src/syntx_mcp/tools/memory.py#L92)
	- `memory_search(...)` — [src/syntx_mcp/tools/memory.py](src/syntx_mcp/tools/memory.py#L144)
	- `memory_expire(...)` — [src/syntx_mcp/tools/memory.py](src/syntx_mcp/tools/memory.py#L184)
	- `memory_list(...)` — [src/syntx_mcp/tools/memory.py](src/syntx_mcp/tools/memory.py#L205)

#### [src/syntx_mcp/tools/notes.py](src/syntx_mcp/tools/notes.py#L1)
- Purpose: Free-form note create/search/list functionality.
- Helpers:
	- `_now()` — [src/syntx_mcp/tools/notes.py](src/syntx_mcp/tools/notes.py#L20)
	- `_new_id()` — [src/syntx_mcp/tools/notes.py](src/syntx_mcp/tools/notes.py#L24)
- Tools:
	- `note_create(...)` — [src/syntx_mcp/tools/notes.py](src/syntx_mcp/tools/notes.py#L29)
	- `note_search(...)` — [src/syntx_mcp/tools/notes.py](src/syntx_mcp/tools/notes.py#L100)
	- `note_list(...)` — [src/syntx_mcp/tools/notes.py](src/syntx_mcp/tools/notes.py#L145)

#### [src/syntx_mcp/tools/projects.py](src/syntx_mcp/tools/projects.py#L1)
- Purpose: Project node management and semantic project search.
- Helpers:
	- `_now()` — [src/syntx_mcp/tools/projects.py](src/syntx_mcp/tools/projects.py#L20)
	- `_new_id()` — [src/syntx_mcp/tools/projects.py](src/syntx_mcp/tools/projects.py#L24)
- Tools:
	- `project_create(...)` — [src/syntx_mcp/tools/projects.py](src/syntx_mcp/tools/projects.py#L29)
	- `project_get(...)` — [src/syntx_mcp/tools/projects.py](src/syntx_mcp/tools/projects.py#L71)
	- `project_list(...)` — [src/syntx_mcp/tools/projects.py](src/syntx_mcp/tools/projects.py#L101)
	- `project_search(...)` — [src/syntx_mcp/tools/projects.py](src/syntx_mcp/tools/projects.py#L125)

#### [src/syntx_mcp/tools/tasks.py](src/syntx_mcp/tools/tasks.py#L1)
- Purpose: Task lifecycle management and linking to decisions/violations.
- Helpers:
	- `_now()` — [src/syntx_mcp/tools/tasks.py](src/syntx_mcp/tools/tasks.py#L20)
	- `_new_id()` — [src/syntx_mcp/tools/tasks.py](src/syntx_mcp/tools/tasks.py#L24)
- Tools:
	- `task_create(...)` — [src/syntx_mcp/tools/tasks.py](src/syntx_mcp/tools/tasks.py#L29)
	- `task_update(...)` — [src/syntx_mcp/tools/tasks.py](src/syntx_mcp/tools/tasks.py#L97)
	- `task_get(...)` — [src/syntx_mcp/tools/tasks.py](src/syntx_mcp/tools/tasks.py#L150)
	- `task_search(...)` — [src/syntx_mcp/tools/tasks.py](src/syntx_mcp/tools/tasks.py#L215)
	- `task_link_decision(...)` — [src/syntx_mcp/tools/tasks.py](src/syntx_mcp/tools/tasks.py#L257)
	- `task_link_violation(...)` — [src/syntx_mcp/tools/tasks.py](src/syntx_mcp/tools/tasks.py#L274)
	- `task_block(...)` — [src/syntx_mcp/tools/tasks.py](src/syntx_mcp/tools/tasks.py#L291)

#### [src/syntx_mcp/tools/violations.py](src/syntx_mcp/tools/violations.py#L1)
- Purpose: Record and manage audit violations and their lifecycle.
- Helpers:
	- `_now()` — [src/syntx_mcp/tools/violations.py](src/syntx_mcp/tools/violations.py#L25)
	- `_new_id()` — [src/syntx_mcp/tools/violations.py](src/syntx_mcp/tools/violations.py#L29)
- Tools:
	- `violation_record(...)` — [src/syntx_mcp/tools/violations.py](src/syntx_mcp/tools/violations.py#L34)
	- `violation_resolve(...)` — [src/syntx_mcp/tools/violations.py](src/syntx_mcp/tools/violations.py#L108)
	- `violation_recur(...)` — [src/syntx_mcp/tools/violations.py](src/syntx_mcp/tools/violations.py#L129)
	- `violation_search(...)` — [src/syntx_mcp/tools/violations.py](src/syntx_mcp/tools/violations.py#L211)
	- `violation_list(...)` — [src/syntx_mcp/tools/violations.py](src/syntx_mcp/tools/violations.py#L260)

### Dependencies (may need updates)
| File | Relationship |
|------|--------------|
| [src/syntx_mcp/server.py](src/syntx_mcp/server.py#L1) | mounts tool modules and depends on `db`, `embeddings`, and `tools` modules |
| [src/syntx_mcp/agents/audit_agent.py](src/syntx_mcp/agents/audit_agent.py#L1) | used by `tools/audit.py` and depends on file IO helpers and `pydantic_ai` Agent runtime |
| All `tools/*` modules | Depend on `db.get_conn()` and `embeddings.embed()` for storage and semantic search |

### Test Files
| Test | Coverage |
|------|----------|
| tests/test_audit.py | Exercises audit tool/agent integration |
| tests/test_db.py | Tests DB bootstrap and connection helpers in `db.py` |
| tests/test_tools.py | Covers common tool behaviors across `tools/` modules |

### Reference Patterns
| File | Pattern |
|------|---------|
| [src/syntx_mcp/tools/audit.py](src/syntx_mcp/tools/audit.py#L1) | Example pattern for invoking an Agent and streaming results |
| [src/syntx_mcp/agents/audit_agent.py](src/syntx_mcp/agents/audit_agent.py#L1) | Agent/tool wiring and definition of agent-side tools |

### Risk Assessment
- [ ] Breaking changes to public API (package exports)
- [ ] Database migrations needed (if DB schema changes)
- [ ] Configuration changes required (env vars, Ollama models, DB paths)

Generated: Expanded context map with functions, start-line links and short descriptions.

