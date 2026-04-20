# Task 029: Base Agent Architecture — Stateless Global Instances with RunContext Injection

**Status:** Planning
**Priority:** High
**Blocked by:** None (foundational)
**Blocks:** Tasks 030 (Workflows), 031 (Prompts), 033 (Tools), 034 (Services)
**Complexity:** MEDIUM

## Problem Statement

Base agents currently mix static configuration and runtime state in ways that make them difficult to test, instrument, and reuse across workflows. State accumulation on `RunContext` (e.g., `_decision_state`, `_task_state`, `ctx._fixer_patches`) violates the stateless-global-instance design principle. Duplicated agents like `audit_agent` vs `preloaded_audit_agent` exist only to branch on a prompt condition that should be data-driven.

The goal is to ensure all 12 agents (auditor, architect, triage, mapper, router, rule_injector, mechanic, scribe, guard, sentry, chat, agent_builder) are globally instantiated, stateless service objects where all mutable context flows through typed `@dataclass` dependencies injected via `RunContext`.

## Goals

1. **Unify agent instances:** Remove duplicate agents; use a single instance with mode-driven prompt branching via deps.
2. **Move state to dataclass deps:** Replace `ctx.__dict__` monkey-patching with proper `@dataclass` fields.
3. **Establish agent inventory:** Document all 12 agents by group (orchestration, audit, document, fix, map, validate, builder).
4. **Enforce prompt-cache discipline:** Keep agent constructors minimal; push all task context into `@agent.system_prompt` functions.
5. **Formalize agent-local tools:** Document `@agent.tool` scope and ensure they are never exposed as MCP tools.
6. **Improve injection testing:** Enable isolated agent testing with mocked deps and tools.

## Non-Goals

- Implementing code-based skills (Task 032).
- Adding new agents beyond the current 12.
- Changing the `Agent` framework itself (that's a Pydantic AI concern).
- Full workflow integration (Task 030).

## Current State

### Agents Implemented

| Group | Agent | File | Current Issues |
|-------|-------|------|-----------------|
| **Orchestration** | `orchestrator_agent` | `agents/orchestrator_agent.py` | Registers six sub-agents; state leakage via `SUBAGENT_REGISTRY` |
| | `router_agent` | `agents/router_agent.py` | Produces `RouterDecision`; clean interface |
| **Audit** | `audit_agent` | `agents/audit/audit_agent.py` | Clean, file-reading pattern |
| | `preloaded_audit_agent` | `agents/audit/audit_agent.py` | **DUPLICATE** — differs only on prompt branch |
| | `rule_injector_agent` | `agents/audit/rule_injector_agent.py` | Clean rule curation pattern |
| **Document** | `decision_agent` | `agents/document/decision_agent.py` | Uses `extra_file_context` branching; clean |
| | `task_agent` | `agents/document/task_agent.py` | Clean decomposition pattern |
| | `scribe_agent` | `agents/document/scribe_agent.py` | Needs verification on integration |
| | `triage_agent` | `agents/document/triage_agent.py` | Needs verification on integration |
| **Fix** | `fixer_agent` | `agents/fix/fixer_agent.py` | State monkey-patched via `ctx._fixer_patches` |
| **Map** | `map_agent` | `agents/map/map_agent.py` | Clean pattern |
| | `chat_agent` | `agents/map/chat_agent.py` | Incomplete; retrieval loop TBD |
| | `diagram_agent` | `agents/map/diagram_agent.py` | Placeholder; Mermaid C4 output TBD |
| **Validate** | `sentry_agent` | `agents/validate/sentry_agent.py` | Clean; runs at `ModelTier.MICRO` |
| | `validation_agent` | `agents/validate/validation_agent.py` | Clean; deterministic guards |
| **Builder** | `agent_builder` | `agents/builder/agent_builder.py` | New; designs helper-agent specs |

### Key Violations

| Violation | Location | Impact |
|-----------|----------|--------|
| `_decision_state` monkey-patched | `decision_agent` | State leaks across runs; untestable |
| `_task_state` monkey-patched | `task_agent` | Same issue |
| `_fixer_patches` monkey-patched | `fixer_agent` | Same issue |
| Duplicate agents | `audit_agent` vs `preloaded_audit_agent` | Maintenance debt; divergence risk |
| `agents/discovery.py` role unclear | `discovery.py` | Overlaps with `router_agent` intent resolution |

## Target Files

### Modifications

```
src/mem_graph/agents/audit/audit_agent.py
  - Merge preloaded_audit_agent logic into single audit_agent with mode: Literal["standalone", "preloaded"]
  - Move state fields into AuditDependencies

src/mem_graph/agents/document/decision_agent.py
  - Add _decision_state to DecisionDependencies instead of ctx.__dict__

src/mem_graph/agents/document/task_agent.py
  - Add _task_state to TaskDependencies instead of ctx.__dict__

src/mem_graph/agents/fix/fixer_agent.py
  - Move _fixer_patches to FixerDependencies instead of ctx.__dict__

src/mem_graph/agents/validate/sentry_agent.py
  - Verify agent-local tool scope; ensure isolation

src/mem_graph/agents/map/chat_agent.py
  - Complete interactive discovery loop
  - Verify tool scope and memory integration

src/mem_graph/agents/map/diagram_agent.py
  - Implement Mermaid C4 diagram generation
  - Integrate with decision/task context

src/mem_graph/agents/builder/agent_builder.py
  - Verify helper-agent spec validation
  - Ensure YAML output format

src/mem_graph/agents/discovery.py
  - Document role or consolidate with router_agent
```

### New Files

```
src/mem_graph/agents/base.py
  - Define AGENT_BASE_SETTINGS (shared temperature, top_p, defer_model_check flags)
  - Document agent instantiation pattern
  - Document agent-local tool pattern

src/mem_graph/agents/__init__.py
  - Export all 12 global agent instances
  - Define AGENT_GROUPS dict for orchestration reflection
```

## Implementation Phases

### Phase 1: Consolidate and Audit (Sprint 1)

- [ ] Merge `preloaded_audit_agent` into `audit_agent` with `mode` field in `AuditDependencies`.
- [ ] Update `AuditDependencies` dataclass:
  ```python
  @dataclass
  class AuditDependencies:
      package_path: str
      mode: Literal["standalone", "preloaded"] = "standalone"
      rules: list[AuditRule] = field(default_factory=...)
      extra_file_context: str = ""
      # ... rest of fields
  ```
- [ ] Update `build_system_prompt` to branch on `ctx.deps.mode` instead of presence of `extra_file_context`.
- [ ] Remove `preloaded_audit_agent` from exports.
- [ ] Verify no callers reference the removed agent.

### Phase 2: Move Accumulated State to Deps (Sprint 1–2)

**`decision_agent`:**
- [ ] Add `_decision_state: DecisionAccumulator = field(default_factory=...)` to `DecisionDependencies`.
  ```python
  @dataclass
  class DecisionAccumulator:
      reviews: list[DecisionReview] = field(default_factory=list)
      summary: str = ""
  ```
- [ ] Replace all `ctx._decision_state` assignments with `ctx.deps._decision_state`.
- [ ] Update agent-local tools to read/write through `ctx.deps._decision_state`.

**`task_agent`:**
- [ ] Add `_task_state: TaskAccumulator` to `TaskDependencies`.
  ```python
  @dataclass
  class TaskAccumulator:
      tasks: list[Task] = field(default_factory=list)
      identified_blockers: list[str] = field(default_factory=list)
  ```
- [ ] Replace all `ctx._task_state` with `ctx.deps._task_state`.

**`fixer_agent`:**
- [ ] Add `_fixer_patches: list[FilePatch] = field(default_factory=list)` to `FixerDependencies`.
- [ ] Replace all `ctx._fixer_patches` with `ctx.deps._fixer_patches`.

### Phase 3: Verify Agent-Local Tool Scope (Sprint 2)

For each agent with `@agent.tool` decorators (audit_agent, decision_agent, task_agent, fixer_agent, sentry_agent, map_agent):
- [ ] Confirm tool is NOT exported in `tools/__init__.py` or listed in MCP registry.
- [ ] Confirm tool is only called from within the agent's `@agent.run()` callback.
- [ ] Document tool in agent's docstring: `# Agent-local tools: list_files, process_batch, finalize_report`.
- [ ] Add a type hint comment: `@agent.tool  # Scope: agent-local only`.

### Phase 4: Establish Agent Factory and Inventory (Sprint 2)

- [ ] Create `src/mem_graph/agents/base.py`:
  ```python
  from dataclasses import dataclass
  from typing import Literal

  @dataclass
  class AgentConfig:
      """Shared settings for all agents."""
      defer_model_check: bool = True
      temperature: float = 0.5  # overridable per-agent
      top_p: float = 0.9

  AGENT_BASE_CONFIG = AgentConfig()

  AGENT_GROUPS = {
      "orchestration": ["orchestrator_agent", "router_agent"],
      "audit": ["audit_agent", "rule_injector_agent"],
      "document": ["decision_agent", "task_agent", "scribe_agent", "triage_agent"],
      "fix": ["fixer_agent"],
      "map": ["map_agent", "chat_agent", "diagram_agent"],
      "validate": ["sentry_agent", "validation_agent"],
      "builder": ["agent_builder"],
  }
  ```

- [ ] Update `src/mem_graph/agents/__init__.py` to export all 12 agents:
  ```python
  from .orchestrator_agent import orchestrator_agent
  from .router_agent import router_agent
  from .audit import audit_agent, rule_injector_agent
  from .document import decision_agent, task_agent, scribe_agent, triage_agent
  from .fix import fixer_agent
  from .map import map_agent, chat_agent, diagram_agent
  from .validate import sentry_agent, validation_agent
  from .builder import agent_builder

  __all__ = [
      "orchestrator_agent", "router_agent",
      "audit_agent", "rule_injector_agent",
      "decision_agent", "task_agent", "scribe_agent", "triage_agent",
      "fixer_agent",
      "map_agent", "chat_agent", "diagram_agent",
      "sentry_agent", "validation_agent",
      "agent_builder",
  ]
  ```

- [ ] Create `docs/planning/design/agents/00-agent-inventory.md`:
  ```markdown
  # Agent Inventory (Verified Q2 2026)

  | Agent | Group | Input Type | Output Type | Persona | Tier |
  |-------|-------|-----------|-------------|---------|------|
  | orchestrator_agent | Orchestration | OrchestratorInput | OrchestratorReport | — | TURBO |
  | ... (12 rows) |
  ```

### Phase 5: Complete Missing Agents (Sprint 3)

**`chat_agent`:**
- [ ] Implement interactive discovery loop for conversational queries.
- [ ] Add `ChatDependencies` with `graph_context: str`, `memory_history: list[Turn]`.
- [ ] Integrate with `memory_recall` tool for graph-grounded answers.
- [ ] Add eval case: grounds answer in at least one node ID.

**`diagram_agent`:**
- [ ] Implement Mermaid C4 diagram generation from codebase structure.
- [ ] Add `DiagramDependencies` with `target_feature: str`, `scope: Literal["system", "container", "component"]`.
- [ ] Integrate output with `decision_agent` and `task_agent` for architecture decisions.
- [ ] Add eval case: produces valid Mermaid syntax.

**`triage_agent`:**
- [ ] Verify deduplication logic (identical `rule + file_path` → merge).
- [ ] Verify severity promotion logic (wide blast-radius → escalate).
- [ ] Add eval cases: dedup two violations, promote severity.

### Phase 6: Documentation and Validation (Sprint 3–4)

- [ ] Write `docs/planning/design/agents/01-agent-initialization-guide.md`:
  ```markdown
  # Agent Initialization Guide

  ## Stateless Global Instance Pattern

  Every agent is instantiated once at module load:
  ```python
  audit_agent: Agent[AuditDependencies, AuditReport] = Agent(
      AGENT_MODEL,
      name="audit",
      deps_type=AuditDependencies,
      output_type=AuditReport,
      model_settings=config_model_settings(temperature=0.2, top_p=0.9),
      defer_model_check=DEFER_AGENT_MODEL_CHECK,
  )
  ```

  Mutable context ALWAYS flows through a @dataclass:
  ```python
  @dataclass
  class AuditDependencies:
      package_path: str
      rules: list[AuditRule] = field(default_factory=list)
      mode: Literal["standalone", "preloaded"] = "standalone"
      # No state fields; they cause coupling and untestability.
  ```
  ```

- [ ] Add a validation script to check that no `ctx.__dict__` assignments occur in any agent file.
  ```python
  # scripts/validate_agent_statelessness.py
  def check_no_ctx_dict_mutation(agent_files):
      for file in agent_files:
          content = read_file(file)
          assert "ctx.__dict__" not in content, f"State leak in {file}"
          assert not re.search(r"ctx\._\w+\s*=", content), f"Monkey-patch in {file}"
  ```

## Acceptance Criteria

1. **No duplicate agents:** Only one `audit_agent` instance exists; `preloaded_audit_agent` is removed.
2. **No state on `ctx`:** No `ctx._*` assignments anywhere in agent code; all state in deps dataclasses.
3. **All 12 agents exported:** `agents/__init__.py` exports all agents; importable as `from mem_graph.agents import audit_agent, ...`.
4. **Agent-local tools documented:** Each agent file lists its tools with `# Agent-local tools: ...` comments.
5. **Agent factory established:** `AGENT_GROUPS` dict enables orchestration reflection.
6. **Missing agents completed:** `chat_agent` and `diagram_agent` have working implementations.
7. **Validation script passes:** Custom script confirms no state pollution in any agent file.

## Test Plan

```bash
# Run agent tests in isolation
uv run pytest tests/agents/ -q

# Check for state leaks
python scripts/validate_agent_statelessness.py

# Verify all 12 agents can be imported
python -c "from mem_graph.agents import *; print('All agents imported OK')"

# Run agent evals (existing suite)
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run mem-graph-evals audit fix document map validate --mode fixture

# Broad integration check
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/ -q -k "agent"
```

## Dependencies

- Pydantic AI framework (no changes needed).
- `config_model_settings()` function for temperature/top_p overrides.
- Task 026 for workflow integration.

## Notes

- Agent consolidation is a prerequisite for dynamic agent selection in workflows (Task 030).
- The state-to-deps migration enables testing agents without full orchestration wiring.
- The agent inventory document becomes the source of truth for tool activation policies (Task 033).
