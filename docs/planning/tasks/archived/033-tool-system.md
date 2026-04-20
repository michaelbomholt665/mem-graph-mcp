# Task 033: Tool System — Tiered MCP Tools with Outcome-Oriented Design

**Status:** Planning
**Priority:** High
**Blocked by:** Task 029 (Base Agent Architecture)
**Blocks:** Task 027 Phase 1–7 (CLI Command Catalog)
**Complexity:** MEDIUM

## Problem Statement

The tool surface is growing without clear organization. Some tools are always loaded (Tier 1), some are namespace-searchable (Tier 2), and some are agent-local or invisible (Tier 3). There's no formal distinction between tiers in code. Filesystem tools are exposed as Tier 2 when they should be Tier 3 (building blocks for agents, not user-facing). Low-level DB operations leak service-level logic onto the MCP surface.

The goal is to:
1. **Formalize three-tier system** with explicit markers.
2. **Reorganize tools by outcome** — high-level user stories, not primitives.
3. **Demote filesystem tools to Tier 3** — agents access them via `@agent.tool` wrappers.
4. **Extract graph query logic to services** — Tier 2 tools call services, not raw DB operations.
5. **Keep Tier 1 small** — ≤8 tools, always loaded.
6. **Enable dynamic tool activation** — `tools_activate(namespace=...)` for discovery.

## Goals

1. **Add formal Tier markers:** `@tier_1_tool`, `@tier_2_tool`, `@hidden_tool` decorators or separate imports.
2. **Reorganize Tier 2 tools** by namespace: `memory`, `work`, `agents`, `background`, `integrations`.
3. **Demote filesystem tools:** Move `file_read`, `file_grep`, `file_search`, `file_list` to Tier 3; agents wrap them.
4. **Create outcome-oriented tools:** E.g., `task_decompose_feature()` calls `task_agent.run()` internally — one tool, complete story.
5. **Extract service layer:** Move low-level DB ops from tools into `services/` so tools stay thin.
6. **Verify agent-local tool isolation:** Confirm no agent-local tools leak into MCP surface.

## Non-Goals

- Adding new command-specific MCP tools (Task 027).
- Redesigning the FastMCP server itself.
- Building a web UI for tool discovery.

## Current State

### Existing Tool Inventory

**Tier 1 — Always Loaded (2):**
- `memory_recall` (resources/memory/memory.py)
- `memory_capture_session` (resources/memory/memory.py)
- `confirm_action` (confirmations.py)
- `request_human_approval` (confirmations.py)

**Tier 2 — Searchable (Partial List):**

| Namespace | Tools | Status |
|-----------|-------|--------|
| `memory` | `conversation_list`, `conversation_get`, `conversation_search`, `note_create`, `note_search`, `note_list` | Defined |
| `work` | `project_create`, `task_create`, `decision_create`, `violation_create`, `task_decompose_feature` | Defined |
| `agents` | `audit_package`, `audit_package_batch`, `map_codebase`, `orchestrator_run`, `triage_violations` | Defined |
| `background` | `background_task_status`, `background_task_list` | Defined |
| `integrations` | `jina_search`, `jina_read_url`, `jina_embed` | Defined |

**Tier 3 — Agent-Local / Invisible:**
- `list_files`, `process_batch` (audit_agent)
- `finalize_report` (audit_agent, decision_agent, task_agent)
- `file_read`, `file_grep`, `file_search`, `file_list` (filesystem primitives, exposed but should be hidden)
- `parse_file`, `parse_directory`, `extract_symbols` (tree-sitter pipeline)
- `graph_search`, `graph_traverse`, `graph_get_node`, + 20+ low-level DB ops

### Issues

| Issue | Impact |
|-------|--------|
| No formal Tier markers in code | Hard to enforce tier boundaries |
| Filesystem primitives exposed as Tier 2 | Bloats user-facing MCP surface |
| `graph_queries.py` (25KB) exposes raw DB ops | Service logic leaked onto MCP layer |
| `audit_package` and `audit_package_batch` partially overlap | Consolidation needed |
| No `@hidden_tool` decorator | Agent-local tools could accidentally leak |

## Target Files

### New Files

```
src/mem_graph/tools/markers.py
  - Define @tier_1_tool, @tier_2_tool, @hidden_tool decorators
  - Define tool tier constants

src/mem_graph/tools/tier_registry.py
  - ToolRegistry class to track which tools belong in which tier
  - Validation on server startup

src/mem_graph/services/graph_context_service.py
  - Extract query helpers from tools/graph/graph_queries.py
  - Provide high-level graph query abstractions

src/mem_graph/services/graph_writer_service.py
  - Shared node-write helper for report_writer.py and violation_writer.py
```

### Modifications

```
src/mem_graph/tools/__init__.py
  - Import tier decorators
  - Export tier-aware tool registry

src/mem_graph/tools/memory/memory.py
  - Add @tier_1_tool marker to memory_recall, memory_capture_session

src/mem_graph/tools/memory/conversation.py
  - Add @tier_2_tool marker

src/mem_graph/tools/memory/notes.py
  - Add @tier_2_tool marker

src/mem_graph/tools/work/projects.py
  - Add @tier_2_tool marker

src/mem_graph/tools/work/tasks.py
  - Add @tier_2_tool marker
  - Update task_decompose_feature() to internally call task_agent.run()

src/mem_graph/tools/work/decisions.py
  - Add @tier_2_tool marker

src/mem_graph/tools/work/violations.py
  - Add @tier_2_tool marker

src/mem_graph/tools/agents/audit.py
  - Add @tier_2_tool marker
  - Consolidate audit_package and audit_package_batch

src/mem_graph/tools/agents/map.py
  - Add @tier_2_tool marker
  - Ensure map_codebase, map_package are outcome-oriented

src/mem_graph/tools/agents/orchestrator.py
  - Add @tier_2_tool marker
  - Extract routing logic to services/

src/mem_graph/tools/agents/triage.py
  - Add @tier_2_tool marker

src/mem_graph/tools/agents/diagrams.py
  - Add @tier_2_tool marker

src/mem_graph/tools/background/task_status.py
  - Add @tier_2_tool marker

src/mem_graph/tools/background/progress.py
  - Add @hidden_tool marker (internal progress reporting only)

src/mem_graph/tools/integrations/jina.py
  - Add @tier_2_tool marker

src/mem_graph/tools/filesystem/filesystem.py
  - Add @hidden_tool marker (demote to Tier 3)

src/mem_graph/tools/filesystem/status.py
  - Add @hidden_tool marker

src/mem_graph/tools/filesystem/tree.py
  - Add @hidden_tool marker

src/mem_graph/tools/graph/graph_queries.py
  - Add @hidden_tool marker to all tools
  - Move to Tier 3
  - Extract service-level logic to services/graph_context_service.py

src/mem_graph/tools/graph/resources.py
  - Add @hidden_tool marker

src/mem_graph/tools/code/parser.py
  - Add @hidden_tool marker

src/mem_graph/tools/sandbox/session.py
  - Add @hidden_tool marker

src/mem_graph/server.py
  - Integrate ToolRegistry validation on startup
  - Ensure MCP server only registers Tier 1 + Tier 2 tools
  - Implement tools_activate(namespace=...) to lazily load Tier 2 namespaces
```

### New Agents/Wrapping

```
src/mem_graph/agents/audit/audit_agent.py
  - Keep existing @agent.tool wrappers: list_files, process_batch, finalize_report
  - Document as "Agent-local tools; not MCP-exposed"

src/mem_graph/agents/document/decision_agent.py
  - Verify agent-local tool scope

src/mem_graph/agents/document/task_agent.py
  - Verify agent-local tool scope

src/mem_graph/agents/fix/fixer_agent.py
  - Verify agent-local tool scope

src/mem_graph/agents/map/map_agent.py
  - Verify agent-local tool scope

src/mem_graph/agents/validate/sentry_agent.py
  - Verify agent-local tool scope
```

## Implementation Phases

### Phase 1: Define Tier Markers (Sprint 1)

**Create `tools/markers.py`:**
- [x] Define decorators:
  ```python
  from functools import wraps
  from typing import Callable

  TIER_1 = "tier_1"
  TIER_2 = "tier_2"
  TIER_3 = "tier_3"

  def tier_1_tool(func: Callable) -> Callable:
      """Mark tool as Tier 1: always loaded, visible to users."""
      func._tool_tier = TIER_1
      return func

  def tier_2_tool(func: Callable) -> Callable:
      """Mark tool as Tier 2: searchable by namespace, user-visible."""
      func._tool_tier = TIER_2
      return func

  def hidden_tool(func: Callable) -> Callable:
      """Mark tool as Tier 3: agent-local or invisible, not exposed to MCP clients."""
      func._tool_tier = TIER_3
      return func

  def get_tool_tier(func: Callable) -> str:
      """Get the tier of a tool function."""
      return getattr(func, "_tool_tier", TIER_2)  # default to Tier 2
  ```

**Create `tools/tier_registry.py`:**
- [x] Define validation registry:
  ```python
  class ToolRegistry:
      def __init__(self):
          self.tier_1_tools: list[str] = []
          self.tier_2_tools: dict[str, list[str]] = {}  # namespace -> [tool names]
          self.tier_3_tools: list[str] = []

      def register_tool(self, name: str, tier: str, namespace: str | None = None) -> None:
          if tier == TIER_1:
              self.tier_1_tools.append(name)
          elif tier == TIER_2:
              ns = namespace or "misc"
              self.tier_2_tools.setdefault(ns, []).append(name)
          elif tier == TIER_3:
              self.tier_3_tools.append(name)

      def validate(self) -> list[str]:
          """Check that Tier 1 has ≤8 tools."""
          errors = []
          if len(self.tier_1_tools) > 8:
              errors.append(f"Tier 1 has {len(self.tier_1_tools)} tools; max is 8")
          return errors

      def get_tier_1(self) -> list[str]:
          return self.tier_1_tools

      def get_tier_2_namespace(self, namespace: str) -> list[str]:
          return self.tier_2_tools.get(namespace, [])
  ```

### Phase 2: Mark All Existing Tools (Sprint 1)

**Add markers to all tool files:**
- [x] Audit tools:
  ```python
  @tier_2_tool
  @mcp.tool()
  async def audit_package(
      package_path: str,
      project_id: str,
      skill_name: str = "python_quality",
  ) -> dict:
      """Run a full code audit on a package and store findings."""
      # ... implementation
  ```

- [x] Tier 1 tools (memory):
  ```python
  @tier_1_tool
  @mcp.tool()
  async def memory_recall(...) -> dict:
      ...

  @tier_1_tool
  @mcp.tool()
  async def memory_capture_session(...) -> dict:
      ...

  @tier_1_tool  # Consider promoting from Tier 2
  @mcp.tool()
  async def memory_search(...) -> dict:
      ...
  ```

- [x] Confirmations (Tier 1):
  ```python
  @tier_1_tool
  @mcp.tool()
  async def confirm_action(...) -> dict:
      ...
  ```

- [x] Filesystem tools (demote to Tier 3):
  ```python
  @hidden_tool
  @mcp.tool()
  async def file_read(...) -> str:
      ...

  @hidden_tool
  @mcp.tool()
  async def file_list(...) -> list[str]:
      ...
  ```

- [x] Graph queries (demote to Tier 3):
  ```python
  @hidden_tool
  @mcp.tool()
  async def graph_search(...) -> list[dict]:
      ...

  @hidden_tool
  @mcp.tool()
  async def graph_traverse(...) -> dict:
      ...
  ```

### Phase 3: Extract Service-Level Logic (Sprint 1–2)

**Create `services/graph_context_service.py`:**
- [x] Move high-level query helpers from `tools/graph/graph_queries.py`:
  ```python
  class GraphContextService:
      async def query_violations(self, project_id: str) -> list[Violation]:
          """Get open violations for a project."""
          # Extract from tools/graph/graph_queries.py _state_query_violations()

      async def query_decisions(self, project_id: str) -> list[Decision]:
          """Get recent decisions for a project."""

      async def query_map(self, project_id: str) -> dict:
          """Get codebase map (features, relationships)."""

      async def query_schema_counts(self) -> dict:
          """Get counts of nodes in DB by type."""

      async def query_indexes(self) -> list[dict]:
          """Get index status."""
  ```

- [x] Tools call the service, not raw DB:
  ```python
  # Before (in tools/graph/graph_queries.py):
  @hidden_tool
  async def graph_get_violations(project_id: str) -> list[dict]:
      conn = get_connection()
      query = """MATCH (p:Project)-[:HAS_VIOLATION]->(v:Violation) ..."""
      results = await conn.run(query, {"project_id": project_id})
      return results

  # After:
  graph_service = GraphContextService()

  @hidden_tool
  async def graph_get_violations(project_id: str) -> list[dict]:
      violations = await graph_service.query_violations(project_id)
      return [v.model_dump() for v in violations]
  ```

**Create `services/graph_writer_service.py`:**
- [x] Extract shared node-write patterns:
  ```python
  class GraphWriterService:
      async def write_node(
          self,
          label: str,
          properties: dict,
          parent_id: str | None = None,
          parent_label: str | None = None,
          relationship_name: str = "HAS_CHILD",
      ) -> str:
          """Write a node to the graph and return its ID."""
          # Common pattern from report_writer.py and violation_writer.py

      async def write_relationship(
          self,
          from_id: str,
          to_id: str,
          rel_name: str,
          properties: dict | None = None,
      ) -> None:
          """Write a relationship between two nodes."""
  ```

- [x] Refactor `services/report_writer.py` and `services/violation_writer.py` to use it.

### Phase 4: Consolidate Overlapping Tools (Sprint 2)

**Merge `audit_package` and `audit_package_batch`:**
- [x] Create unified tool:
  ```python
  @tier_2_tool
  @mcp.tool()
  async def audit_package(
      package_path: str,
      project_id: str,
      skill_name: str = "python_quality",
      batch: bool = False,  # New: if True, chunk and process in batches
  ) -> dict:
      """Run a code audit on a package (single or batched mode)."""

      if batch:
          # Use batch processing for large codebases
          report = await run_package_audit(package_path)
      else:
          # Single agent run
          deps = AuditDependencies(...)
          result = await audit_agent.run(..., deps=deps)
          report = result.output

      await report_writer.write_audit_report(report, project_id=project_id)
      return report.model_dump(mode="json")
  ```

### Phase 5: Make Outcome-Oriented Tools (Sprint 2)

**Verify tools complete full stories:**
- [x] `task_decompose_feature()` example:
  ```python
  @tier_2_tool
  @mcp.tool()
  async def task_decompose_feature(
      project_id: str,
      feature_description: str,
  ) -> DecompositionReport:
      """Decompose a feature into sequenced tasks with TDD phases.

      This is an outcome-oriented tool: callers get a complete report
      without needing to understand agents, graphs, or intermediate steps.
      """

      # Internally orchestrates:
      # 1. Load project context from graph
      deps = TaskDependencies(
          feature_description=feature_description,
          project_id=project_id,
          # ... load from graph
      )

      # 2. Run task_agent
      result = await task_agent.run(..., deps=deps)

      # 3. Persist to graph
      # 4. Return structured output
      return result.output
  ```

- [x] Review all Tier 2 tools for outcome-completeness.

### Phase 6: Server-Level Validation (Sprint 2–3)

**Update server startup:**
- [x] Integrate `ToolRegistry` in `src/mem_graph/server.py`:
  ```python
  async def startup():
      # Scan all tool files
      registry = ToolRegistry()

      # Register each tool by scanning decorators
      for tool in all_mcp_tools():
          tier = get_tool_tier(tool)
          namespace = get_tool_namespace(tool)
          registry.register_tool(tool.__name__, tier, namespace)

      # Validate
      errors = registry.validate()
      if errors:
          raise RuntimeError(f"Tool registry errors: {errors}")

      # Store registry for tools_activate() to use
      ctx.tool_registry = registry
  ```

- [x] Implement `tools_activate(namespace)`:
  ```python
  @mcp.tool()
  async def tools_activate(namespace: str) -> dict:
      """Activate tools in a namespace (Tier 2 discovery)."""
      registry = get_context().tool_registry
      tools = registry.get_tier_2_namespace(namespace)
      return {
          "namespace": namespace,
          "activated_tools": tools,
          "count": len(tools),
      }
  ```

### Phase 7: Agent-Local Tool Verification (Sprint 3)

**Ensure no agent-local tools leak:**
- [x] Add validation script `scripts/validate_agent_tool_scope.py`:
  ```python
  def validate_agent_tool_scope():
      """Check that agent-local @agent.tool decorators are not in MCP namespace."""

      mcp_tools = set(all_mcp_tools())

      for agent_file in glob("src/mem_graph/agents/**/*.py"):
          content = read_file(agent_file)

          # Find @agent.tool definitions
          agent_local_tools = re.findall(r"@\w+_agent\.tool\s+async def (\w+)", content)

          # Check none are in MCP
          for tool_name in agent_local_tools:
              assert tool_name not in mcp_tools, \
                  f"Agent-local tool {tool_name} leaked into MCP surface!"
  ```

- [x] Run validation on every agent file.

### Phase 8: Documentation (Sprint 3)

- [x] Create `docs/planning/design/tools/tool-tier-system.md`:
  ```markdown
  # Tool Tier System

  ## Tier 1 — Always Loaded (≤8 tools)

  High-level orchestrator tools solving complete outcomes. Never require namespace activation.

  | Tool | Purpose |
  |------|---------|
  | memory_recall | Retrieve from session memory |
  | memory_capture_session | Persist session to graph |
  | confirm_action | Gate destructive operations |

  ## Tier 2 — Searchable (Namespaces)

  Domain tools discovered via `tools_activate(namespace=...)`. Outcome-oriented; complete stories.

  | Namespace | Tools | Purpose |
  |-----------|-------|---------|
  | memory | conversation_list, note_create, ... | Session memory ops |
  | work | project_create, task_decompose_feature, ... | Project/task management |
  | agents | audit_package, map_codebase, ... | Agent invocation |

  ## Tier 3 — Invisible / Agent-Local

  Agent building blocks and primitives. Never exposed to MCP clients.
  ```

## Acceptance Criteria

1. **Tier markers defined:** `@tier_1_tool`, `@tier_2_tool`, `@hidden_tool` decorators in use.
2. **All tools marked:** Every MCP tool has a tier marker.
3. **Tier 1 ≤8 tools:** No more than 8 tools loaded always.
4. **Tier 2 organized by namespace:** memory, work, agents, background, integrations.
5. **Filesystem tools demoted:** `file_*` tools are Tier 3 `@hidden_tool`.
6. **Graph tools demoted:** `graph_*` tools are Tier 3 `@hidden_tool`.
7. **Service layer extracted:** `graph_context_service.py` and `graph_writer_service.py` created.
8. **Tools call services:** Tier 2 tools call service layer, not raw DB.
9. **Tools are outcome-oriented:** Each tool completes a full story (e.g., `task_decompose_feature`).
10. **Agent-local tools isolated:** No agent-local `@agent.tool` leaks into MCP surface.
11. **Server validation passes:** `ToolRegistry.validate()` confirms tier structure.

## Test Plan

```bash
# Test tier markers
uv run pytest tests/tools/test_tier_markers.py -q

# Test tier registry
uv run pytest tests/tools/test_tier_registry.py -q

# Validate agent tool scope
python scripts/validate_agent_tool_scope.py

# Test service extractions
uv run pytest tests/services/test_graph_context_service.py -q
uv run pytest tests/services/test_graph_writer_service.py -q

# Regression on all tools
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/tools/ -q

# Broad gate
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/ -q
```

## Dependencies

- Task 029 (Base Agent Architecture) — agent deps structure.
- Task 034 (Services Layer) — coordination on service extraction.

## Notes

- Tier 1 list should be validated empirically; if promoting `memory_search` saves latency, do it.
- Task 027 (CLI Command Catalog) depends on this task's tier system being complete.
- Namespace activation is a key optimization for latency in interactive workflows.
