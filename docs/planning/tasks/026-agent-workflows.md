# Task 026: Resource-Driven Agent Workflows and Profiled Orchestration

**Status:** Planning
**Priority:** High
**Blocked by:** None
**Blocks:** Research workflow rollout, web acquisition workflow rollout, and eval-driven skill hardening

## Problem Statement

Workflow orchestration logic is currently split across agent modules, which makes reuse harder and creates drift risk between workflow runtime and workflow metadata.

Current examples:

- `src/mem_graph/agents/orchestrator_graph.py`
- `src/mem_graph/agents/workflow_graph.py`
- `src/mem_graph/agents/discovery.py` (static workflow metadata)

This task introduces workflow resources as first-class project assets and refactors orchestration so the main AI acts as the orchestrator over profile-selected, reusable workflows.

## Goals

1. Move workflow definitions out of agent modules into workflow resources.
2. Add workflow profiles by task size (`small`, `medium`, `large`) and task type.
3. Add reasoning workflows with a required ReAct self-challenge step before final choice.
4. Implement multi-agent orchestration where the main AI orchestrates specialized sub-agents.
5. Implement iterative package review/audit workflow:
   - Read 4-5 files in one package.
   - Produce/update report section.
   - Continue to next package and edit the same report until complete.
6. Update existing agents/tools to consume the new workflow resources and runtime selectors.

## Scope

### In Scope

- Workflow resource schema, loading, validation, and selection.
- Runtime execution graph(s) that consume selected workflow resources.
- Profile-based routing and stage policies.
- Reasoning policy integration (ReAct + challenge).
- Package-batched audit/report loop.
- Refactor existing workflow entry points to use new structure.
- Tests and docs updates for workflow migration.

### Out of Scope

- Rewriting all individual sub-agent domain logic.
- Replacing existing tool interfaces unless needed for compatibility.
- Full autonomous web crawling strategy details (covered by follow-up tasks).

## Target Architecture

Keep top-level small while introducing subfolders for workflow resources.

```text
src/mem_graph/
  resources/
    workflows/
      __init__.py
      models.py
      profiles.py
      task_types.py
      reasoning.py
      registry.py
      selector.py
      visualization.py
  workflows/
    __init__.py
    runtime/
      __init__.py
      orchestrator_runtime.py
      package_audit_runtime.py
      managed_workflow_runtime.py
```

## Python-First Workflow Resource Policy

Workflow resources are Python-defined, not YAML-defined.

- Profiles, reasoning policies, task-type mappings, and stage options are typed Python models.
- Registry loading is import-time deterministic and validated via Pydantic model checks.
- Conditional step options are computed in code from current runtime context/state.
- Visualization metadata is generated from the same Python registry to prevent drift.

## Workflow Profiles

Define profile intent and constraints as typed Python resources, not hardcoded per-agent logic.

### Small Profile

- Minimal stage count.
- Single pass where possible.
- Tight tool budget and low fan-out.
- Default for low-file, low-risk tasks.

### Medium Profile

- Standard staged flow.
- Limited parallel sub-agent fan-out.
- One validation/retry cycle allowed by default.

### Large Profile

- Full staged orchestration with milestone loops.
- Parallel read/analyze waves followed by implementation/validation waves.
- Explicit checkpoints and recovery points.

## Reasoning Workflow Requirements

Default reasoning mode must be ReAct with a mandatory challenge step.

Required sequence:

1. Observe context.
2. Draft initial action/hypothesis.
3. Challenge initial action:
   - Ask what could be wrong.
   - Check for missing evidence.
   - Evaluate at least one alternative.
4. Make final choice and execute.

This is not free-form chain-of-thought logging; it is a deterministic reasoning policy for safer decisions.

Optional reasoning profile for high-ambiguity tasks:

- Bounded Tree-of-Thought (small width/depth only).
- Must include pruning criteria and budget caps.

## Main-AI Orchestrated Multi-Agent Workflow

Main AI responsibilities:

- Select workflow profile from resources (`size + task_type + risk`).
- Select reasoning policy.
- Build stage plan and dependency order.
- Launch and coordinate sub-agents.
- Aggregate stage artifacts.
- Enforce retry/stop policies.
- Emit final summary and memory-bank update payload.

Sub-agent responsibilities:

- Execute focused domain steps (map, audit, decision, fix, validate, docs, monitoring).
- Return typed artifacts only (no orchestration ownership).

## Iterative Package Review/Audit Workflow

Add a package-level audit runtime that operates incrementally.

Per package:

1. Discover in-scope files for package.
2. Chunk files into groups of 4-5.
3. For each chunk:
   - Read/analyze files.
   - Produce findings.
   - Update running report (append new findings or edit prior conclusions).
4. Close package summary.
5. Move to next package and continue report updates.

Finalization:

- Deduplicate repeated findings across packages.
- Re-rank severity globally.
- Produce final report and unresolved follow-up list.

## Migration Requirements (Move Workflows Out of Current Agents)

Migrate workflow ownership from:

- `src/mem_graph/agents/workflow_graph.py`
- `src/mem_graph/agents/orchestrator_graph.py`

To:

- `src/mem_graph/resources/workflows/*` (definitions and selectors)
- `src/mem_graph/workflows/runtime/*` (execution runtime)

Update call sites and metadata:

- `src/mem_graph/tools/agents/orchestrator.py`
- `src/mem_graph/agents/router_agent.py`
- `src/mem_graph/agents/discovery.py` (source workflow metadata from registry, not duplicated static graph declarations)

Backward compatibility:

- Keep compatibility wrappers in old modules during migration window.
- Mark wrappers deprecated and remove in a follow-up cleanup task.

## Skill Selection and Evals Integration

Tie workflow stage capability needs to internal skill selection.

- Parent/main AI selects capabilities by task category/type, not concrete skill names.
- Sub-agent/runtime resolves skill from registry.
- Use eval outcomes to update dispatch weighting.
- Low-performing skills are quarantined (opt-out) and flagged for update, not silently deleted.

## Implementation Phases

### Phase 1: Resource Model and Registry

- Add workflow resource models, loader, and validation.
- Add typed profile/task-type/reasoning modules.
- Add selector for profile + reasoning policy.

### Phase 2: Runtime Extraction

- Move execution logic into `workflows/runtime`.
- Keep typed state models and stage artifacts.
- Add compatibility wrappers in existing agent modules.

### Phase 3: Orchestrator Integration

- Update router/tool entrypoints to select workflow resources first.
- Main AI orchestrates sub-agent execution from selected runtime plan.

### Phase 4: Package Audit Loop

- Implement 4-5 file chunk iteration per package.
- Add incremental report update/edit behavior through run lifecycle.

### Phase 5: Discovery and Metadata

- Replace static workflow metadata with registry-driven metadata.
- Ensure dashboard/API visibility aligns with active runtime workflows.

### Phase 6: Tests and Documentation

- Add unit tests for resource parsing, selector logic, and reasoning policy enforcement.
- Add integration tests for small/medium/large workflows and package audit iteration.
- Update docs and task references.

## Acceptance Criteria

- Workflow definitions live under `src/mem_graph/resources/workflows/`.
- Workflow resources are Python-based (no YAML workflow definitions).
- Existing agents no longer own primary workflow definitions.
- Runtime uses selected profiles (`small`, `medium`, `large`) for orchestration behavior.
- ReAct self-challenge is enforced before final action choice.
- Main AI orchestrates sub-agents using typed stage artifacts.
- Package audit flow processes files in 4-5 file chunks and incrementally updates one report through completion.
- `agents/discovery.py` workflow metadata is registry-driven (no duplicated static workflow definitions).
- Existing workflow entry tools continue working via updated internals.

## Implementation Checklist

- [x] Add workflow resource models and validation.
- [x] Create typed workflow profiles (`small`, `medium`, `large`) in Python.
- [x] Create typed reasoning policies (`react_challenge`, optional bounded ToT) in Python.
- [x] Build workflow registry and selector.
- [x] Generate workflow visualization metadata from the Python workflow registry.
- [x] Move runtime execution out of current agent workflow modules.
- [x] Add compatibility wrappers and update imports/callers.
- [x] Integrate profile selection into router/orchestrator entrypoints.
- [x] Implement package audit loop with 4-5 file batching.
- [x] Implement incremental report update/edit strategy across packages.
- [x] Make workflow discovery metadata registry-driven.
- [x] Integrate skill-resolution hooks + eval-score-aware dispatch policy.
- [x] Add/extend tests for profiles, reasoning policy, orchestration, and audit loop.
- [x] Update documentation and follow-up deprecation notes.
