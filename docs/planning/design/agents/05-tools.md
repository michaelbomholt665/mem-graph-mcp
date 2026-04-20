# 05 — Tools

## Principle

Tools are FastMCP-registered functions that agents call during inference. The surface should be small and outcome-oriented — each tool completes a full agent story rather than exposing a single primitive. Complexity lives in `services/`.

Tools exist in two contexts:
1. **MCP tools** — registered with the FastMCP server, callable by any connected AI client
2. **Agent-local tools** — decorated with `@agent.tool`, scoped exclusively to one agent (e.g. `list_files`, `process_batch`, `finalize_report`)

This document covers **MCP tools** (the `tools/` namespace). Agent-local tools are documented in `01-base-agents.md`.

---

## Three Tiers

### Tier 1 — Visible (few, always loaded)
High-level orchestrator tools. Solve complete outcomes. Always in the agent's tool context. The goal is to keep this list short — 5–8 tools maximum.

### Tier 2 — Searchable (some, namespace-activated)
Domain tools discovered via `tools_activate(namespace=...)`. Not in the main context window unless requested. The default path for most MCP tools.

### Tier 3 — Invisible / Agent-only (many)
Granular primitives used exclusively by workflow nodes or agent-internal `@agent.tool` functions. **Never** appear in the MCP client's tool list. File system tools belong here — most agents need access to files, but file I/O is a primitive that feeds into an agent-local tool call, not a standalone user-facing action.

> The filesystem namespace (`file_read`, `file_grep`, `file_search`, `file_list`) is Tier 3. It is an agent building block, not a user-facing surface. Agents access it through their own `@agent.tool` wrappers (`list_files`, `process_batch`) which apply scope constraints, byte limits, and extension filters.

---

## Current Tool Inventory

### Tier 1 — Always loaded

| File | Tools | Description | Decision |
|------|-------|-------------|----------|
| `tools/memory/memory.py` | `memory_recall`, `memory_capture_session` | Session memory and graph-based recall | **Keep Tier 1** |
| `tools/confirmations.py` | `confirm_action`, `request_human_approval` | Human-in-the-loop gates for destructive ops | **Keep Tier 1** |

**Promotion candidates** (pending usage-data confirmation):

| Tool | Current tier | Rationale for Tier 1 |
|------|-------------|----------------------|
| `memory_search` | Tier 2 | High call frequency in interactive sessions |
| `conversation_list` | Tier 2 | Near-universal use; avoids a namespace activation round-trip |

The Tier 1 list must stay at **≤ 8 tools total**. Promote only if usage data confirms the saving
on namespace activation round-trips outweighs the context-window cost.

### Tier 2 — Searchable by namespace

**`memory` namespace:**

| File | Tools |
|------|-------|
| `tools/memory/conversation.py` | `conversation_list`, `conversation_get`, `conversation_search` |
| `tools/memory/notes.py` | `note_create`, `note_search`, `note_list` |

**`work` namespace:**

| File | Tools |
|------|-------|
| `tools/work/projects.py` | `project_create`, `project_get`, `project_search`, `project_list`, `project_update` |
| `tools/work/tasks.py` | `task_create`, `task_get`, `task_search`, `task_update`, `task_decompose_feature`, `task_list_open` |
| `tools/work/decisions.py` | `decision_create`, `decision_search`, `decision_review`, `decision_update` |
| `tools/work/violations.py` | `violation_create`, `violation_search`, `violation_update`, `violation_triage` |

**`agents` namespace:**

| File | Tools |
|------|-------|
| `tools/agents/audit.py` | `audit_package`, `audit_package_batch` |
| `tools/agents/map.py` | `map_codebase`, `map_package` |
| `tools/agents/orchestrator.py` | `orchestrator_run`, `autopilot_remediate` |
| `tools/agents/triage.py` | `triage_violations` |
| `tools/agents/diagrams.py` | `generate_diagram` |

**`background` namespace:**

| File | Tools |
|------|-------|
| `tools/background/task_status.py` | `background_task_status`, `background_task_list` |

**`integrations` namespace:**

| File | Tools |
|------|-------|
| `tools/integrations/jina.py` | `jina_search`, `jina_read_url`, `jina_embed` |

### Tier 3 — Invisible / workflow-only

| File | Tools | Notes |
|------|-------|-------|
| `tools/filesystem/filesystem.py` | `file_read`, `file_search`, `file_grep`, `file_list` | Agent building-block only |
| `tools/filesystem/status.py` | `filesystem_status`, `repo_status` | Git status, workspace info |
| `tools/filesystem/tree.py` | `file_tree` | Directory tree |
| `tools/graph/graph_queries.py` | `graph_search`, `graph_traverse`, `graph_get_node`, + many more | Low-level graph primitives |
| `tools/graph/resources.py` | `graph_list_resources` | Resource enumeration |
| `tools/sandbox/session.py` | `sandbox_create_session`, `sandbox_finalize` | Workflow sandbox lifecycle |
| `tools/background/progress.py` | `background_progress_update` | Internal progress reporting |
| `tools/code/parser.py` | `parse_file`, `parse_directory`, `extract_symbols` | Tree-sitter; parser pipeline only |

---

## Namespace Activation Pattern

```
# Default (Tier 1 always present):
memory_recall, memory_capture_session, confirm_action, ...

# After tools_activate(namespace='work'):
+ project_create, task_create, decision_create, violation_create, ...

# After tools_activate(namespace='agents'):
+ audit_package, map_codebase, orchestrator_run, ...
```

---

## Outcome-Oriented Design

**Good:** `task_decompose_feature(project_id, feature_description) → DecompositionReport`
— Internally calls `task_agent.run()` with graph context already loaded. One call, complete story.

**Avoid:** `db_create_node(label, props)`, `db_get_node(id)`, `db_link_nodes(from_id, to_id, rel)
— Three primitives the caller must manually orchestrate. Service-level logic leaking into the tool surface.

---

## Improvement Opportunities

| Issue | Recommendation |
|-------|---------------|
| `tools/graph/graph_queries.py` (25KB) exposes many low-level DB ops on the MCP surface | Move to Tier 3; expose only outcome-level tools (e.g. `graph_get_project_health`) as Tier 2 |
| `tools/agents/orchestrator.py` (15KB) mixes routing logic with the MCP wrapper | Move routing logic to `services/`; keep wrapper to argument marshalling only |
| `audit_package` and `audit_package_batch` partially overlap | Consolidate to one `audit_package` tool with a `batch: bool` flag |
| Filesystem tools are currently Tier 2 (searchable) | Demote to Tier 3 — they are agent building blocks, not user-facing actions |
| No formal marker distinguishes Tier 3 from Tier 2 in code | Add a `@hidden_tool` decorator or a separate `internal_tools` import path that the MCP server never registers |

---

## Command Catalog Integration (Task 027)

The CLI Command Catalog provides outcome-oriented wrappers that bridge the gap between Tier 3
primitives and Tier 1 user-facing actions. See `docs/planning/tasks/027-commands.md`.

| CLI Command | Tool Tier | Backs into | Notes |
|-------------|-----------|-----------|-------|
| `agent audit` | Tier 2 | `audit_package`, `audit_package_batch` | Routes through existing `agents` namespace |
| `agent map` | Tier 2 | `map_codebase`, `map_package` | Cartographer output feeds `task_agent` |
| `agent fix` | Tier 2 | `orchestrator_run`, `autopilot_remediate` | Service-backed; uses `violation_writer.py` |
| `agent validate` | Tier 2 + T3 | `triage_violations` + agent-local tools | Guard node; no direct LLM tool exposure |
| `agent document` | Tier 2 | `task_decompose_feature`, `decision_create` | Work namespace |
| `code parse` | Tier 3 | `parse_file`, `parse_directory` | Pipeline-only; never user-facing |
| `embed code` | Tier 3 | `CodeEmbedService` | Service call; no MCP surface |
| `db inspect` | Tier 3 | `graph_queries.py` templates | Named templates; raw Cypher gated |
| `python repl` | Tier 1 | CodeMode snippet execution | Outcome-level diagnostic |
| `shell execute` | Tier 1 | Allowlisted argv | Strict allowlist; no `shell=True` |
| `toolchain python` | Tier 2 wrapper | ruff + mypy + pytest | Outcome-oriented; one call, complete story |
| `toolchain go` | Tier 2 wrapper | gofumpt + go test + govulncheck | Same model as `toolchain python` |

> **Key insight:** High-level commands like `toolchain go` and `toolchain python` act as the
> preferred "outcome-oriented" wrappers. Instead of an agent calling multiple granular tools, a
> single command handles formatting, testing, and scanning — matching the Tier 1 philosophy.
