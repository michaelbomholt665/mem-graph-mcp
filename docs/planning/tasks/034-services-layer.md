# Task 034: Services Layer — Business Logic Extraction and Decoupling

**Status:** Planning
**Priority:** Medium
**Blocked by:** Task 029 (Base Agent Architecture), Task 033 (Tool System)
**Blocks:** Tasks 035–036
**Complexity:** MEDIUM

## Problem Statement

Business logic is scattered across tools, agents, and graph nodes. `orchestrator_graph.py` contains raw Cypher queries and DB writes. `tools/graph/graph_queries.py` (25KB) exposes low-level DB operations that belong in a service layer. Duplication exists between `text_embed_service.py` and `jina_embedder.py` (retry logic). Tools directly manipulate the database instead of calling services.

The goal is to ensure the `services/` layer contains all complex logic (embedding, DB writes, graph queries, report rendering, deduplication) while tools and agents stay thin: marshal arguments, call a service, return results.

## Goals

1. **Extract query helpers:** Move high-level graph operations from tools and graph nodes into a dedicated `GraphContextService`.
2. **Extract write helpers:** Create `GraphWriterService` for shared node-write patterns.
3. **Consolidate embedding retry logic:** Extract common patterns to a base class.
4. **Formalize service boundaries:** Tools ↔ Services ↔ DB; never Tools ↔ DB direct.
5. **Improve service testability:** Services testable with mocked DB connections; tools testable with mocked services.
6. **Create domain-specific services:** For report writing, violation management, summarization.

## Non-Goals

- Redesigning the database schema.
- Adding new business features.
- Building an ORM (Ladybug DB is already abstracted).

## Current State

### Existing Services (13 files, ~200KB)

| File | Role | Status |
|------|------|--------|
| `text_embed_service.py` | Ollama text embedding | Complete; 15KB |
| `code_embed_service.py` | Code-specific embedding | Complete; 8KB |
| `jina_embedder.py` | Jina AI fallback | Complete; 10KB |
| `jina_common.py` | Jina HTTP client | Complete; 5KB |
| `memory.py` | Graph memory reads/writes | Complete; 12KB |
| `search.py` | Unified search (hybrid, vector, keyword) | Complete; 15KB |
| `fingerprint.py` | Content deduplication | Complete; 5KB |
| `report_writer.py` | AuditReport → graph persistence | Complete; 8KB |
| `violation_writer.py` | Violation node creation/updates | Complete; 10KB |
| `summarizer.py` | LLM-powered content summarization | Complete; 6KB |
| `task_queue.py` | In-process async task queue | Complete; 10KB |
| `sandbox_sessions.py` | Workflow sandbox tracking | Complete; 3KB |

### Known Service Layer Violations

| Location | Issue | Remedy |
|----------|-------|--------|
| `orchestrator_graph.py` — `_state_query_violations()`, `_state_query_decisions()`, `_state_query_map()` | Raw Cypher in graph node | Extract to `GraphContextService` |
| `orchestrator_graph.py` — `_state_write_note()` | Inline DB write | Call `services/memory.py` |
| `tools/graph/graph_queries.py` (25KB) | Extensive query construction logic | Extract to `GraphContextService` |
| `tools/agents/orchestrator.py` (15KB) | Complex argument resolution | Move to `services/` |
| Duplicate retry logic | `text_embed_service.py` and `jina_embedder.py` | Extract base class |
| No summarizer instrumentation | Missing Logfire spans | Add `traced_span()` |

## Target Files

### New Services

```
src/mem_graph/services/graph_context_service.py
  - GraphContextService class with high-level query methods
  - Queries: violations, decisions, map, schema counts, indexes

src/mem_graph/services/graph_writer_service.py
  - Shared node-write and relationship-write helpers
  - Used by report_writer.py and violation_writer.py

src/mem_graph/services/embed_client.py
  - EmbedClientBase with shared retry logic
  - Used by text_embed_service.py and jina_embedder.py

src/mem_graph/services/command_db.py (Task 027 Phase 3 integration)
  - Named Cypher query templates for `db inspect`, `db query-template`
  - Wrapper over GraphContextService for CLI commands

src/mem_graph/services/command_shell.py (Task 027 Phase 4 integration)
  - Allowlisted argv execution for `toolchain *`, `lint fix`

src/mem_graph/services/command_evals.py (Task 027 Phase 6 integration)
  - `eval gate` runner wrapper

src/mem_graph/services/command_parse_stage.py (Task 027 Phase 5 integration)
  - Parser staging without immediate graph ingest

src/mem_graph/services/command_embed.py (Task 027 Phase 6 integration)
  - `embed documents` and `embed code` wrappers
```

### Modifications

```
src/mem_graph/agents/orchestrator_graph.py
  - Replace _state_query_violations() with call to graph_context_service
  - Replace _state_query_decisions() with call to graph_context_service
  - Replace _state_query_map() with call to graph_context_service
  - Replace _state_write_note() with call to memory.py

src/mem_graph/tools/graph/graph_queries.py
  - Demote all tools to @hidden_tool
  - Extract query logic to GraphContextService
  - Keep thin wrapper layer

src/mem_graph/tools/agents/orchestrator.py
  - Extract routing logic to services/
  - Keep tool layer thin

src/mem_graph/services/text_embed_service.py
  - Inherit from EmbedClientBase
  - Share retry logic

src/mem_graph/services/jina_embedder.py
  - Inherit from EmbedClientBase
  - Share retry logic

src/mem_graph/services/report_writer.py
  - Use GraphWriterService for node creation
  - Reduce boilerplate

src/mem_graph/services/violation_writer.py
  - Use GraphWriterService for node creation
  - Reduce boilerplate

src/mem_graph/services/summarizer.py
  - Add Logfire instrumentation around LLM calls
```

## Implementation Phases

### Phase 1: Extract GraphContextService (Sprint 1–2)

**Create `services/graph_context_service.py`:**
- [x] Design high-level query interface:
  ```python
  class GraphContextService:
      def __init__(self, conn: Connection):
          self.conn = conn

      async def query_violations(
          self,
          project_id: str,
          status: str | None = None,
      ) -> list[Violation]:
          """Get violations for a project, optionally filtered by status."""
          # Extract from orchestrator_graph.py _state_query_violations()

      async def query_decisions(
          self,
          project_id: str,
          limit: int = 10,
      ) -> list[Decision]:
          """Get recent decisions for a project."""

      async def query_map(
          self,
          project_id: str,
      ) -> dict:
          """Get codebase map (features, relationships, entry points)."""

      async def query_schema_counts(self) -> dict:
          """Get counts of nodes in DB by type."""
          # SELECT count(*) WHERE node:Label

      async def query_indexes(self) -> list[dict]:
          """Get index status and coverage."""

      async def query_project_health(self, project_id: str) -> dict:
          """Aggregate: violation counts, recent decisions, map coverage."""
          return {
              "violations": await self.query_violations(project_id),
              "decisions": await self.query_decisions(project_id),
              "map": await self.query_map(project_id),
          }
  ```

- [x] Extract query logic from `orchestrator_graph.py`:
  ```python
  # Before (in orchestrator_graph.py):
  def _state_query_violations(project_id: str) -> list[dict]:
      query = """
          MATCH (p:Project {id: $project_id})-[:HAS_VIOLATION]->(v:Violation)
          WHERE v.status = 'open'
          RETURN v
      """
      return db_run(query, {"project_id": project_id})

  # After (in graph_context_service.py):
  async def query_violations(self, project_id: str) -> list[Violation]:
      # Same Cypher, but wrapped in typed interface
      query = """..."""
      results = await self.conn.run(query, {"project_id": project_id})
      return [Violation.model_validate(r) for r in results]
  ```

- [x] Integrate into orchestrator_graph.py:
  ```python
  class ContextGatherNode(BaseNode[AutopilotState]):
      async def run(self, ctx: GraphRunContext[AutopilotState]) -> AutopilotState:
          graph_service = GraphContextService(get_db_connection())

          ctx.state.context_violations = await graph_service.query_violations(
              ctx.state.project_id
          )
          ctx.state.context_decisions = await graph_service.query_decisions(
              ctx.state.project_id
          )
          ctx.state.context_map = await graph_service.query_map(
              ctx.state.project_id
          )

          return ctx.state
  ```

### Phase 2: Extract GraphWriterService (Sprint 2)

**Create `services/graph_writer_service.py`:**
- [x] Design node-write abstraction:
  ```python
  class GraphWriterService:
      def __init__(self, conn: Connection):
          self.conn = conn

      async def write_node(
          self,
          label: str,
          properties: dict,
          return_id: bool = True,
      ) -> str:
          """Write a node to the graph and return its ID."""
          # Common: CREATE (n:Label {...}) RETURN id(n)

      async def write_relationship(
          self,
          from_id: str,
          to_id: str,
          rel_type: str,
          properties: dict | None = None,
      ) -> None:
          """Write a relationship between nodes."""
          # CREATE (f)-[:REL_TYPE {...}]->(t)

      async def write_parent_child(
          self,
          parent_id: str,
          parent_label: str,
          child_data: dict,
          child_label: str,
          rel_type: str = "HAS_CHILD",
      ) -> str:
          """Write a child node and link to parent."""
          # Combines write_node + write_relationship
  ```

- [x] Refactor `report_writer.py`:
  ```python
  # Before:
  async def write_audit_report(report: AuditReport, project_id: str) -> None:
      conn = get_db_connection()

      # Create Report node
      query = "CREATE (r:AuditReport {...}) RETURN id(r)"
      [report_id] = await conn.run(query, {... properties ...})

      # Link to project
      query = f"MATCH (p:Project {{id: $pid}}), (r:AuditReport {{id: $rid}}) CREATE (p)-[:HAS_REPORT]->(r)"
      await conn.run(query, {"pid": project_id, "rid": report_id})

      # ... repeat for file results, findings

  # After:
  async def write_audit_report(report: AuditReport, project_id: str) -> None:
      writer = GraphWriterService(get_db_connection())

      report_id = await writer.write_node(
          "AuditReport",
          {
              "package_path": report.package_path,
              "summary": report.summary,
              ...
          },
      )

      await writer.write_relationship(
          project_id,
          report_id,
          "HAS_AUDIT_REPORT",
      )

      # File results
      for file_result in report.file_results:
          file_id = await writer.write_parent_child(
              report_id, "AuditReport",
              file_result.model_dump(),
              "FileAuditResult",
              rel_type="HAS_FILE_RESULT",
          )
  ```

- [x] Apply same pattern to `violation_writer.py`.

### Phase 3: Consolidate Embedding Retry Logic (Sprint 2)

**Create `services/embed_client.py`:**
- [x] Base class for embedding clients:
  ```python
  class EmbedClientBase:
      def __init__(
          self,
          model: str,
          max_retries: int = 3,
          backoff_factor: float = 2.0,
      ):
          self.model = model
          self.max_retries = max_retries
          self.backoff_factor = backoff_factor

      async def _retry_with_backoff(self, fn: Callable, *args, **kwargs):
          """Retry with exponential backoff."""
          for attempt in range(self.max_retries):
              try:
                  return await fn(*args, **kwargs)
              except Exception as e:
                  if attempt == self.max_retries - 1:
                      raise
                  wait_time = self.backoff_factor ** attempt
                  await asyncio.sleep(wait_time)

      async def embed_text(self, text: str) -> list[float]:
          """Override in subclasses."""
          raise NotImplementedError
  ```

- [x] Refactor `TextEmbedService`:
  ```python
  class TextEmbedService(EmbedClientBase):
      def __init__(self, model: str, dim: int):
          super().__init__(model)
          self.dim = dim

      async def embed_text(self, text: str) -> list[float]:
          async def _call():
              # Ollama call logic
              pass
          return await self._retry_with_backoff(_call)
  ```

- [x] Refactor `JinaEmbedder`:
  ```python
  class JinaEmbedder(EmbedClientBase):
      async def embed_text(self, text: str) -> list[float]:
          async def _call():
              # Jina call logic
              pass
          return await self._retry_with_backoff(_call)
  ```

### Phase 4: Add Summarizer Instrumentation (Sprint 2)

**Update `services/summarizer.py`:**
- [x] Add Logfire spans:
  ```python
  from mem_graph.observability.logfire_setup import traced_span

  async def summarize_session(content: str) -> str:
      with traced_span("summarizer.summarize_session"):
          # LLM call here
          summary = await call_model(content)
          return summary
  ```

### Phase 5: Extract Orchestrator Logic (Sprint 2–3)

**Create `services/orchestrator_service.py` (optional, if needed by Task 027):**
- [ ] Wrap routing logic:
  ```python
  class OrchestratorService:
      async def route_request(self, request: dict) -> RouterDecision:
          """Call router_agent and return decision."""
          deps = RouterDependencies(...)
          result = await router_agent.run(..., deps=deps)
          return result.output

      async def run_autopilot(
          self,
          package_path: str,
          project_id: str,
          language: str,
      ) -> AutopilotResult:
          """Run autopilot graph from start to finish."""
          # Orchestrate graph execution
  ```

- [ ] Update `tools/agents/orchestrator.py` to use it.

### Phase 6: Add Task 027 Services (Sprint 3–4, Integrated with Task 027)

- [ ] `command_db.py` — Named query templates via GraphContextService.
- [ ] `command_shell.py` — Allowlisted argv execution.
- [ ] `command_evals.py` — Eval gate runners.
- [ ] `command_parse_stage.py` — Parser staging.
- [ ] `command_embed.py` — Embedding commands.

(These will be implemented as part of Task 027, not Task 034.)

## Acceptance Criteria

1. **GraphContextService created:** High-level query interface for violations, decisions, map, schema.
2. **GraphWriterService created:** Shared node-write helpers reduce boilerplate in report/violation writers.
3. **Embedding retry logic consolidated:** `EmbedClientBase` eliminates duplication.
4. **Orchestrator graph uses services:** `_state_query_*()` and `_state_write_*()` call services.
5. **Tools call services:** No direct DB access from tool layer.
6. **Summarizer instrumented:** Logfire spans around LLM calls.
7. **No regression:** Existing functionality unchanged.
8. **Services are testable:** Each service can be tested with mocked connections.

## Test Plan

```bash
# Test GraphContextService
uv run pytest tests/services/test_graph_context_service.py -q

# Test GraphWriterService
uv run pytest tests/services/test_graph_writer_service.py -q

# Test embedding consolidation
uv run pytest tests/services/test_embed_client.py -q

# Regression on orchestrator graph
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/workflows/test_orchestrator_graph.py -q

# Regression on all services
uv run pytest tests/services/ -q

# Broad gate
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/ -q
```

## Dependencies

- Task 029 (Base Agent Architecture) — agent deps structure.
- Task 033 (Tool System) — tools call services, not DB directly.
- Ladybug DB connection interface (no changes needed).

## Notes

- Service layer improves testability significantly; each service is independently testable.
- Task 027 Phase 3–6 integrations (command_* services) will add to this foundation but don't need to complete Task 034.
- Future: Consider DI (dependency injection) framework for service instantiation and connection pooling.
