# 06 — Services

## Principle

The `services/` layer encapsulates business logic that tools call. MCP tools and agent-local tools must stay thin — they marshal arguments, call a service, and return the result. All complexity (embedding, DB writes, external APIs, deduplication, report rendering) lives in services.

This decoupling makes each component independently testable: tools can be tested with service mocks; services can be tested without the MCP layer at all.

---

## Current Services Inventory

### Embedding Services

| File | Class / Functions | Purpose |
|------|------------------|---------|
| `services/text_embed_service.py` | `TextEmbedService`, `embed_text()`, `embed_batch()` | Ollama-backed text embedding for memory nodes, notes, decisions, violations |
| `services/code_embed_service.py` | `CodeEmbedService`, `embed_code()`, `embed_code_batch()` | Ollama-backed code-specific embedding using `OLLAMA_CODE_EMBED_MODEL` |
| `services/jina_embedder.py` | `JinaEmbedder`, `embed()` | Jina AI embedding fallback for when Ollama is unavailable |
| `services/jina_common.py` | `jina_request()`, `build_headers()`, auth helpers | Shared HTTP client logic for all Jina API calls |

`TextEmbedService` (15KB, the largest service file) handles:
- Model loading from `OLLAMA_TEXT_EMBED_MODEL` env var
- Request batching and retry logic
- Dimension validation against `OLLAMA_EMBED_DIM`
- Caching to avoid redundant embedding calls

### Memory & Search Services

| File | Class / Functions | Purpose |
|------|------------------|---------|
| `services/memory.py` | `capture_session()`, `recall_memory()`, `search_memory()` | Graph writes and reads for the conversational memory layer |
| `services/search.py` | `hybrid_search()`, `vector_search()`, `keyword_search()` | Unified search entry point over the Ladybug graph |
| `services/fingerprint.py` | `fingerprint_content()`, `fingerprint_file()` | SHA-based content fingerprinting for deduplication |

### Report Services

| File | Class / Functions | Purpose |
|------|------------------|---------|
| `services/report_writer.py` | `write_audit_report()`, `write_audit_finding()` | Persists `AuditReport` and `FileAuditResult` to the graph as structured nodes |
| `services/violation_writer.py` | `write_violation()`, `update_violation_status()`, `deduplicate_violations()` | Creates / updates `Violation` nodes; handles recurrence detection |
| `services/summarizer.py` | `summarize_session()`, `summarize_audit()` | LLM-powered summarisation for long content before graph writes |

### Async / Queue Services

| File | Class / Functions | Purpose |
|------|------------------|---------|
| `services/task_queue.py` | `TaskQueue`, `enqueue()`, `dequeue()`, `task_status()`, `cancel_task()` | In-process async task queue for background agent runs (10KB) |
| `services/sandbox_sessions.py` | `SandboxSessionStore`, `get_session()`, `register_session()` | Thin in-memory session store for workflow sandbox tracking |

---

## Service Call Patterns

### Pattern 1 — Tool calls service, returns structured output

```python
# tools/agents/audit.py
@mcp.tool()
async def audit_package(package_path: str, project_id: str) -> dict:
    """Run a full code audit on a package and store findings."""
    deps = AuditDependencies(package_path=package_path, ...)
    result = await audit_agent.run(prompt, deps=deps)
    report = result.output
    # Service handles graph persistence
    await report_writer.write_audit_report(report, project_id=project_id)
    return report.model_dump(mode="json")
```

### Pattern 2 — Agent-local tool calls service (via deps)

```python
@audit_agent.tool
async def finalize_report(ctx: RunContext[AuditDependencies], summary: str) -> AuditReport:
    file_results = ctx.deps.file_results
    stats = _compute_stats(file_results)   # local helper, not a service
    return AuditReport(...)
```

Note: `_compute_stats` is a pure function in `audit_agent.py`. Moving it to a `services/audit_stats.py` would improve reusability but is not critical since it has no I/O.

### Pattern 3 — Service used in workflow node

```python
# agents/orchestrator_graph.py MemorySyncNode
def _state_write_note(project_id: str, content: str) -> None:
    # This currently does a raw DB write inline in the graph
    # It SHOULD be: await memory_service.write_note(project_id, content)
```

---

## Service → Tool Boundary Violations (Current)

The following locations contain service-level logic that should be extracted:

| Location | Issue |
|----------|-------|
| `orchestrator_graph.py` — `_state_query_violations()`, `_state_query_decisions()`, `_state_query_map()` | Raw Cypher queries embedded in graph node helpers; should call `services/search.py` or a dedicated `graph_context_service.py` |
| `orchestrator_graph.py` — `_state_write_note()` | Inline DB write; should call `services/memory.py` |
| `tools/graph/graph_queries.py` (25KB) | Contains extensive query construction logic that belongs in a `services/graph_service.py` |
| `tools/agents/orchestrator.py` (15KB) | Complex argument resolution and context loading that belongs in `services/` |
| `agents/audit/audit_agent.py` — `_compute_stats()`, `_format_rules_for_prompt()` | Pure utility functions — acceptable as local helpers, but `_format_rules_for_prompt` could live in a `services/rule_formatter.py` |

---

## Service Testing Strategy

Services are the primary unit test target because they carry the actual complexity:

```bash
# Test embedding services with mocked Ollama
uv run pytest tests/test_embeddings.py -q

# Test report and violation writers with temp DB
uv run pytest tests/test_db.py -q

# Test search services
uv run pytest tests/test_search.py -q   # if exists
```

Tools tests should only verify:
1. Correct argument marshalling
2. Service is called with the right arguments
3. Service output is correctly serialised for the MCP response

---

## Improvement Opportunities

All additions stay within existing `services/` — no new top-level folders.

| Issue | Recommendation |
|-------|---------------|
| No `services/graph_context_service.py` | Extract `_state_query_violations()`, `_state_query_decisions()`, `_state_query_map()` from `orchestrator_graph.py` into a `GraphContextService` in `services/` — callable by both graph nodes and MCP tools |
| `task_queue.py` (10KB) does too much | Split into `task_queue.py` (core queue) + `task_executor.py` (agent dispatch), both in `services/` |
| `report_writer.py` and `violation_writer.py` share boilerplate node-link patterns | Extract a shared node-write helper into `services/graph_writer.py` |
| Retry logic duplicated between `text_embed_service.py` and `jina_embedder.py` | Extract to a shared `services/embed_client.py` retry base class |
| `summarizer.py` holds an LLM call but is not instrumented with Logfire spans | Add `traced_span("summarizer.summarize")` around LLM invocations |

**Task 027 (CLI Command Catalog) additions — all in `services/`:**

| New service file | Purpose |
|-----------------|---------|
| `services/command_db.py` | Named Cypher query templates for `db inspect`, `db query-template`, `db cypher` |
| `services/command_shell.py` | Allowlisted argv execution for `toolchain *`, `lint fix`, `shell execute` |
| `services/command_evals.py` | `eval gate` runner; wraps the existing `Evaluator` entry points |
| `services/command_parse_stage.py` | Parser staging without immediate graph ingest (`code stage`, `code commit-index`) |
| `services/command_embed.py` | `embed documents` and `embed code` command wrappers |

All Task 027 additions stay in `services/` — no new namespaces or top-level folders.
