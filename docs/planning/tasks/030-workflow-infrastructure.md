# Task 030: Workflow Infrastructure — FSM-Based Orchestration with Typed State

**Status:** Planning
**Priority:** High
**Blocked by:** Task 029 (Base Agent Architecture)
**Blocks:** Task 031 (Prompts), Tasks 032–036, Task 027 Phase 8 (workflow start)
**Complexity:** LARGE

## Problem Statement

Workflows currently exist in two places (`agents/orchestrator_graph.py`, `agents/workflow_graph.py`) with duplicate infrastructure. The `package_audit_runtime.py` is a raw async loop, not a typed FSM. Planned workflows (29 total) are defined but not yet registered. The reasoning-mode selection (ReAct, Bounded-ToT, Chain-of-Thought) is documented but not wired into graph structure or prompts.

The goal is to:
1. **Unify graph infrastructure** in `workflows/` alongside their runtimes.
2. **Register all 29 planned workflows** with `WorkflowProfile` configuration.
3. **Model package audit as a graph** for consistent tracing and state management.
4. **Wire reasoning modes** into node-level prompt injection so agents self-apply the correct strategy.
5. **Enable profile-selected workflow dispatch** — callers request a task type, the system selects the best `WorkflowProfile` based on file count and language.

## Goals

1. **Move graph definitions:** Relocate `orchestrator_graph.py` and `workflow_graph.py` node classes to `workflows/` to co-locate definitions with runtimes.
2. **Formalize workflow registry:** Implement `WorkflowRegistry` mapping task keys → `WorkflowProfile` objects with stage configs, retry policies, model tier overrides, and metadata.
3. **Register all 29 workflows:** Add Group A workflows (feature_implementation, refactor, research, security_hardening, etc.) in priority order; maintain cross-cutting `research` workflow.
4. **Model package_audit as graph:** Convert `package_audit_runtime.py` to `DiscoverNode → ChunkNode → AnalyzeNode → AggregateNode → End` FSM.
5. **Inject reasoning modes:** Add `reasoning_mode` field to `WorkflowProfile`; inject into stage prompts via `REASONING_MODES` mapping.
6. **Implement profile selector:** Build `selector.select_all(task_key, file_count, language) → WorkflowProfile` logic with overrides for large codebases and model tier adjustments.
7. **Add workflow metadata:** Track workflow complexity, estimated cost, agent roster, required tools, and compatibility ranges.
8. **Define complete workflow lifecycle:** Map all 29 workflows across Phases 1-8 of the software development lifecycle.

- Implementing the full feature_implementation workflow (that's incremental in Task 031+).
- Building a web UI for workflow selection (CLI only for now).
- Changing the pydantic-graph FSM framework itself.
- Detailed prompt engineering (prompts are defined in `reasoning_patterns.md` and `02-recommended_workflows.md`).

## Current State

### Registered Workflows (3)

| Workflow | Runtime File | Complexity | Status |
|----------|--------------|-----------|--------|
| `autopilot_graph` | `workflows/runtime/orchestrator_runtime.py` | Six-node fix pipeline | Complete; used for violations |
| `managed_workflow_graph` | `workflows/runtime/managed_workflow_runtime.py` | Nine-node feature workflow | Complete; uses RouterDecision |
| `package_audit` | `workflows/runtime/package_audit_runtime.py` | Raw async loop | **NOT** a typed FSM; needs refactor |

### Cross-cutting Research Workflow

The `research` workflow (from `02-recommended_workflows.md`) is a **cross-cutting** workflow usable across multiple phases. It is registered once and can be invoked from any phase requiring research activities.

### Planned Workflows (29) — Group A (Ready Now)

| Workflow | Priority | Agents | Mode | Blocker |
|----------|----------|--------|------|---------|
| `feature_implementation` | 1 | sentry, fixer, auditor, scribe | ReAct | None |
| `refactor` | 2 | mapper, fixer, auditor, scribe | ReAct | None |
| `research` | 3 | auditor, scribe | Bounded-ToT | None |
| `security_hardening` | 4 | auditor, fixer, scribe | Bounded-ToT | None |
| `performance_profiling` | 5 | auditor, fixer, scribe | Bounded-ToT | None |
| `adr_authoring` | 6 | scribe | ReAct | None |
| `feature_design` | 6 | scribe, auditor | ReAct | None |
| `schema_design` | 6 | auditor, scribe | Bounded-ToT | None |
| `api_contract_design` | 6 | scribe, auditor | ReAct | None |
| `design_docs` | 6 | scribe | ReAct | None |
| `runbook_authoring` | 6 | scribe | ReAct | None |
| `disaster_recovery` | 6 | auditor, scribe | Bounded-ToT | None |
| `command_design` | 6 | scribe, fixer | ReAct | Needs definition |
| `error_logging_design` | 6 | scribe, auditor | ReAct | None |
| `dependency_audit` | 7 | auditor | ReAct | None |
| `ci_setup` | 7 | scribe, auditor | ReAct | None |
| `docs_generation` | 8 | scribe | ReAct | None |
| `changelog_authoring` | 8 | scribe | ReAct | None |
| `onboarding_docs` | 8 | scribe | ReAct | None |
| `release_preparation` | 9 | scribe, auditor | ReAct | None |
| `deployment_validation` | 9 | auditor | ReAct | None |
| `utility_extraction` | 10 | mapper, fixer, auditor | ReAct | None |
| `implementation_planning` | 11 | router, scribe | ReAct-2 | None |
| `project_scaffold` | 11 | fixer, scribe | ReAct | None |
| **Group B (Blocked):**
| `idea_capture` | — | scribe, chat | ReAct | chat_agent incomplete |
| `requirements_elicitation` | — | scribe, chat | Bounded-ToT | chat_agent incomplete |
| `architecture_design` | — | router, scribe, auditor | Bounded-ToT | diagram_agent incomplete |
| `command_design` | — | scribe, fixer | ReAct | **Unclear lifecycle** |
| `codebase_migration` | — | mapper, fixer, auditor, scribe | Bounded-ToT | Not yet in Group A |
| `code_skeptic` | — | auditor | Bounded-ToT | Not yet in Group A |

### Reasoning Modes (Defined but Not Wired)

| Mode | Pattern | Use Case |
|------|---------|----------|
| `REACT_CHALLENGE` | plan → re-think → design → execute | Most MEDIUM/LARGE workflows |
| `REACT_2` | plan → confirm/improve/drop → design → execute | Iterating on prior work |
| `BOUNDED_TOT` | observe → branch (≤3) → prune → expand → decide | Architectural decisions |
| `CHAIN_OF_THOUGHT` | N parallel paths per step, carry best forward | Multi-step reasoning |

Currently hardcoded per workflow; should be injected via `WorkflowProfile.reasoning_mode`.

### Existing Infrastructure

| File | Purpose | Status |
|------|---------|--------|
| `resources/workflows/registry.py` | Central `WorkflowRegistry` | Skeleton; no entries |
| `resources/workflows/profiles.py` | `WorkflowProfile` dataclass | Defined; not used |
| `resources/workflows/selector.py` | `select_all(task_key, file_count, language)` | Skeleton; no logic |
| `resources/workflows/models.py` | Configuration Pydantic models | Complete (includes `WorkflowMetadata`, `StageConfig`) |
| `resources/workflows/reasoning.py` | Named reasoning pattern constants | Defined (includes `REACT_CHALLENGE`, `REACT_2`, `BOUNDED_TOT`, `COT`) |
| `resources/workflows/visualization.py` | Node-style JSON for graph viz | Stub |

### Reasoning Mode Constants (from `reasoning_patterns.md`)

| Mode | Pattern | Use Case |
|------|---------|----------|
| `REACT_CHALLENGE` | plan → re-think → design → execute | Most MEDIUM/LARGE workflows |
| `REACT_2` | plan → confirm/improve/drop → design → execute | Iterating on prior work |
| `BOUNDED_TOT` | observe → branch (≤3) → prune → expand → decide | Architectural decisions, threat modelling |
| `COT` | N parallel paths per step, carry best forward | Multi-step reasoning where each step reframes the next |

> These map to `ReasoningMode` enum in `models.py`.

## Target Files

### Modifications

```
src/mem_graph/resources/workflows/registry.py
  - Populate WorkflowRegistry with 24 Group A workflows
  - Add registry entry for package_audit as graph-based workflow

src/mem_graph/resources/workflows/profiles.py
  - Add reasoning_mode field to WorkflowProfile
  - Add metadata: complexity, estimated_cost, agent_roster, required_tools

src/mem_graph/resources/workflows/selector.py
  - Implement select_all(task_key, file_count, language) logic
  - Return WorkflowProfile with best-fit reasoning mode

src/mem_graph/resources/workflows/reasoning.py
  - Document reasoning patterns with prompt injection snippets
  - Add templates for each mode (REACT_CHALLENGE, REACT_2, BOUNDED_TOT, COT)

src/mem_graph/workflows/runtime/orchestrator_runtime.py
  - Move node definitions from agents/orchestrator_graph.py to workflows/
  - Update imports in existing callers

src/mem_graph/workflows/runtime/managed_workflow_runtime.py
  - Move node definitions from agents/workflow_graph.py to workflows/
  - Update imports in existing callers

src/mem_graph/workflows/runtime/package_audit_runtime.py
  - Replace async loop with pydantic-graph FSM: DiscoverNode, ChunkNode, AnalyzeNode, AggregateNode, End
  - Add PackageAuditState dataclass with typed fields
  - Update for consistent tracing and state management

src/mem_graph/agents/orchestrator_graph.py
  - Delete or deprecate; link to new location in workflows/

src/mem_graph/agents/workflow_graph.py
  - Delete or deprecate; link to new location in workflows/
```

### New Files

```
src/mem_graph/workflows/__init__.py
  - Export WorkflowProfile, WorkflowRegistry, selector, reasoning modes

src/mem_graph/workflows/runtime/__init__.py
  - Export all runtime graph classes and runtimes

src/mem_graph/resources/workflows/workflow_definitions.py
  - Define all 24 Group A WorkflowProfile objects
  - Use named constants for reasoning modes and agent rosters

docs/planning/design/workflows/workflow-registry-q2-2026.md
  - Document all registered workflows with agent rosters and reasoning modes
```



## Acceptance Criteria

1. **Graph definitions moved:** `orchestrator_graph.py` and `workflow_graph.py` node classes in `workflows/`.
2. **Package audit is a graph FSM:** `DiscoverNode → ChunkNode → AnalyzeNode → AggregateNode → End`.
3. **All 24 Group A workflows registered:** `WORKFLOW_REGISTRY.get("feature_implementation")` returns valid `WorkflowProfile`.
4. **Profile selector implemented:** `select_all()` returns profiles with adjusted reasoning modes and model tiers.
5. **Reasoning modes wired:** Stage prompts include `reasoning_hint` injected from `WorkflowProfile.reasoning_mode`.
6. **Metadata complete:** All profiles have `estimated_cost_tokens`, `estimated_runtime_minutes`, `required_tools`.
7. **No regression:** Existing autopilot and managed workflows work unchanged.

## Test Plan

```bash
# Test graph infrastructure
uv run pytest tests/workflows/test_orchestrator_graph.py -q
uv run pytest tests/workflows/test_managed_workflow_graph.py -q

# Test package audit FSM
uv run pytest tests/workflows/test_package_audit_graph.py -q

# Test registry and selector
uv run pytest tests/workflows/test_registry.py -q
uv run pytest tests/workflows/test_selector.py -q

# Test reasoning mode injection
uv run pytest tests/workflows/test_reasoning_modes.py -q

# Regression on existing workflows
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/ -q -k "autopilot or managed_workflow"

# Broad gate
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/workflows/ -q
```

## Dependencies

- Task 029 (Base Agent Architecture) — agent inventory needed for WorkflowProfile.agent_roster.
- pydantic-graph framework (no changes needed).

## Notes

- Task 027 Phase 8 (workflow start) depends on this task's WorkflowRegistry and selector being complete.
- Group B workflows (chat_agent, diagram_agent dependencies) unblock separately as those agents complete.
- Workflow complexity scores should be validated empirically after first 5 workflows run in production.
