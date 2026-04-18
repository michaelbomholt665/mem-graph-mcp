# Mem-graph Memory MCP Server

Mem-graph Memory is an agent memory store for Mem-graph implemented as an MCP (Model Context Protocol) server. It leverages the FastMCP framework to provide robust capability for capturing and inter-linking conversations, tasks, decisions, notes, and audit violations, enabling semantic recall across AI assistant sessions.

## Server Metadata

Package versioning now has one runtime source of truth: `pyproject.toml`, exported in code as `mem_graph.__version__`. The FastMCP server reuses that value for its advertised version metadata instead of hard-coding a separate string.

Operational metadata is exposed in two stable places:
- The core MCP tool `get_server_info`
- The HTTP endpoint `GET /info`

Both surfaces return the server name, package version, API version, and website URL. The website defaults to `https://github.com/michael/syntx-memory` and can be overridden with `MEM_GRAPH_WEBSITE` in the deployment environment.

Release notes now live in `CHANGELOG.md`.

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

## Observability

OpenTelemetry is now wired into the server lifecycle through `src/mem_graph/observability/`.

- Telemetry is disabled by default unless you explicitly enable it or provide an OTLP exporter endpoint.
- Local debugging can use the built-in console exporter by setting `MEM_GRAPH_OTEL_ENABLED=true` and `MEM_GRAPH_OTEL_CONSOLE_EXPORTER=true`.
- Production exports can be enabled with the standard OTLP environment variables such as `OTEL_EXPORTER_OTLP_ENDPOINT`.
- Structured logs now carry `trace_id` and `span_id` when a request is inside an active span.
- Metrics currently cover tool duration, background task throughput, and graph-query latency/result counts.

Logfire now sits alongside that OTEL path as the live execution recorder for agent runs, tool spans, memory operations, and graph queries.

- Enable it with `MEM_GRAPH_LOGFIRE_ENABLED=true`.
- If `LOGFIRE_TOKEN` is present, telemetry is sent to Logfire automatically; otherwise the bootstrap falls back to a safe tokenless path.
- Pydantic AI instrumentation is enabled with prompt and tool payload content excluded by default. Opt in with `MEM_GRAPH_LOGFIRE_INCLUDE_CONTENT=true` only when you explicitly need that visibility.
- HTTPX spans are instrumented by default without body capture. Set `MEM_GRAPH_LOGFIRE_CAPTURE_HTTPX=true` to capture raw provider payloads when debugging model traffic.
- Existing OTEL exporters continue to work through the same startup path, so Logfire and OTLP exports can run together without racing over the global providers.

The graph-query instrumentation records query class, query fingerprint, parameter count, duration, and row counts. It does not attach raw Cypher text or query parameters to spans.

## Evals

The repository now includes a reusable eval framework under `src/mem_graph/evals/` plus maintained suites for audit, map, fix, validate, and document-oriented agent workflows.

Run the deterministic fixture-backed baseline from the repo root:

```bash
make evals
```

Run a single suite or override the stochastic run count:

```bash
uv run mem-graph-evals --mode fixture audit --runs 1
```

Run the live agent suites when model credentials are configured:

```bash
make evals-live
```

You can also use the direct script entry point:

```bash
uv run python scripts/run_evals.py --mode fixture
```

Write a machine-readable report to disk and optionally persist a compact summary to the graph:

```bash
uv run mem-graph-evals --mode fixture --output build/evals/fixture-report.json
uv run mem-graph-evals --mode fixture --output build/evals/ci-report.json --persist-project-id <project-id> --persist-label ci
```

The default merge gate should stay fast and deterministic: `make evals-ci` runs the fixture suites once and fails if any maintained case regresses. Live suites remain appropriate for release checks and manual investigation because they depend on model credentials and introduce normal LLM variance. Use `make evals-release` before cutting a release when you want that higher-confidence live signal.

The default suite threshold is `0.67`, which means a case must pass at least 2 out of the default 3 runs to be considered healthy. This keeps the foundation useful for stochastic agents without turning every run into a flaky all-or-nothing gate.
