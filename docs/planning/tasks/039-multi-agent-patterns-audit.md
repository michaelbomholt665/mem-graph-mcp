# 039: Multi-Agent Patterns Audit

Why
- `docs/planning/design/agents/11-multi-agent-patterns.md` defines five multi-agent complexity levels and recommends unified `RunUsage` aggregation for a single job or task.
- The codebase already uses delegation and graph-based orchestration heavily, but the usage-tracking story is incomplete.

---

## Current State

### Level 2: Agent Delegation

Observed delegated `agent.run(...)` usage:

- `src/mem_graph/agents/orchestrator_agent.py`
  - delegates to bundled sub-agents during batch processing
  - delegates to `map_agent`
  - delegates to `decision_agent`
- `src/mem_graph/agents/orchestrator_graph.py`
  - `SentryNode` delegates to `sentry_agent`
  - `LogicDraftNode` delegates to `fixer_agent`
  - `StyleDraftNode` delegates to `scribe_agent`
- `src/mem_graph/agents/workflow_graph.py`
  - `ImplementationNode` delegates to `fixer_agent`
  - `AuditNode` delegates to `audit_agent`
  - `DocumentationNode` delegates to `scribe_agent`
  - `ContextMapUpdateNode` delegates to `map_agent`
- `src/mem_graph/agents/map/diagram_agent.py`
  - helper flow delegates to classifier, generator, and describer agents via `.run()`
- `src/mem_graph/tools/agents/orchestrator.py`
  - delegates to `router_agent` for route-only and workflow-plan selection
- `src/mem_graph/workflows/runtime/package_audit_runtime.py`
  - delegates to `audit_agent` while processing package chunks

This is already substantial Level 2 usage.

### Level 3: Programmatic Hand-off

Observed Python-owned orchestration:
- `src/mem_graph/tools/agents/orchestrator.py` selects routes and workflow plans in application code.
- `src/mem_graph/workflows/runtime/*` runtime modules own stage transitions outside agent reasoning.
- `src/mem_graph/agents/workflow_graph.py` exposes a typed Python entrypoint that decides whether stages execute agents or just record stage results.

This codebase uses programmatic control flow in addition to direct delegation.

### Level 4: Graph-based Flow

Observed `pydantic-graph` workflows:
- `src/mem_graph/agents/orchestrator_graph.py`
- `src/mem_graph/agents/workflow_graph.py`
- `src/mem_graph/agents/map/diagram_agent.py`

These modules implement explicit state machines with typed state and node transitions, matching the Level 4 pattern from the design doc.

### Level 5: Deep Agents

Not observed as a complete pattern.
- There is no evidence of recursive planning/self-delegation loops with autonomous replanning boundaries equivalent to the design doc’s “Deep Agents”.
- Some routing and workflow planning exists, but it remains application-directed rather than autonomous recursive delegation.

---

## Gaps Against the Design Doc

### 1. Unified Usage Aggregation Is Missing

Observed gap:
- No `RunUsage` import found under `src/mem_graph`.
- No delegated run site was found passing `usage=ctx.usage`.
- No equivalent shared usage object was found in orchestration paths.

Why this matters:
- The design doc explicitly recommends a single usage object per job/task.
- Without shared usage propagation, telemetry and billing attribution across nested agent runs will be fragmented or unavailable.

### 2. Delegation Contract Is Inconsistent

Observed gap:
- Different orchestration sites pass different subsets of context to delegates.
- Some sites use preloaded file context; others rely on live tools; others pass only a prompt string.

Why this matters:
- Delegation is present, but the handoff contract is not yet standardized.
- That makes behavior harder to reason about and increases the risk of subtle prompt/context drift across workflows.

### 3. Backward-Compatibility Graph Modules Still Exist

Observed in file headers:
- `src/mem_graph/agents/orchestrator_graph.py` states runtime ownership moved to `mem_graph.workflows.runtime.orchestrator_runtime`.
- `src/mem_graph/agents/workflow_graph.py` states runtime ownership moved to `mem_graph.workflows.runtime.managed_workflow_runtime`.

Why this matters:
- The graph modules remain reachable while the runtime modules are the stated primary path.
- This may be intentional for compatibility, but it increases the number of orchestration surfaces that need consistent delegation and usage behavior.

---

## Recommended Work

### A. Introduce Canonical Usage Propagation

Target:
- all delegated `agent.run(...)` sites that belong to one logical job/task

Requirements:
- define the canonical shared usage object at the runtime/orchestrator boundary
- pass it through every nested agent run
- verify telemetry is aggregated across the full chain

### B. Standardize Delegate Handoff Shape

Target:
- `orchestrator_agent.py`
- `orchestrator_graph.py`
- `workflow_graph.py`
- `tools/agents/orchestrator.py`

Requirements:
- document what each delegate receives: prompt, deps, file context, and optionally message history
- prefer explicit clean prompts for specialist delegates unless history is required
- make the distinction between route-only, preloaded, and tool-driven delegates visible in code

### C. Consolidate Orchestration Entry Points

Target:
- runtime modules vs. compatibility graph modules

Requirements:
- decide which modules are canonical execution surfaces
- avoid improving one orchestration path while leaving another semantically stale
- if compatibility modules remain, ensure they share the same usage propagation and delegation semantics

---

## Verification Notes

Grounded observations used for this task:
- Delegated `.run(...)` call sites were found in orchestrator, graph, runtime, tool, and diagram modules.
- `pydantic-graph` is actively used in the graph workflow modules.
- No `RunUsage` or `usage=ctx.usage` usage was found under `src/mem_graph`.
