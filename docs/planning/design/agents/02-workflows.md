# 02 — Workflows

## Principle

Workflows are Python-owned finite state machines. The LLM reasons only within a single node; Python owns routing, retries, state mutation, and aggregation. This is the critical inversion: the graph calls agents, not the other way around.

The two graph libraries in use:
- **`pydantic-graph`** — typed `BaseNode` FSM with `GraphRunContext[State]` threaded through every step
- **`pydantic-evals`** — dataset-backed evaluation framework (see `08-evals.md`)

---

## Reasoning Patterns

Every workflow selects one of three reasoning modes before execution. These are not just documentation — they determine the system-prompt strategy, branching behaviour, and tool budget enforcement inside each node.

### ReAct-Challenge (default)
`plan → re-think → design → execute`

The re-think step is a mandatory self-challenge: "What is wrong with this plan? Is there missing context?" If the challenge surfaces a flaw, the plan restarts. Used by most MEDIUM/LARGE workflows.

**Variant — ReAct 2:** `plan → confirm/improve/drop → design → execute`. The prior decision or draft is surfaced explicitly and the agent must choose: confirm it, improve it, or drop it entirely and restart. Used when iterating on prior work (e.g. `implementation_planning` reviewing a feature design before committing).

### Bounded Tree-of-Thought (`BOUNDED_TOT`)
`observe → branch (≤3) → prune → expand best → decide`

Explores multiple candidate approaches simultaneously, scores them against pruning criteria, eliminates losers, then expands the winning branch. Width and depth are hard-capped (`width=3, depth=2, budget_cap=500`). Used for architectural and strategic decisions where a bad first instinct is expensive to undo.

**Pruning criteria:**
1. Violates an active architectural decision
2. Requires more context than is available
3. Exceeds the tool budget for the current stage
4. Creates a circular dependency

**Chain-of-Thought variant:** Runs `N` parallel answer paths at each step, picks the best, carries only that forward into the next step. Prevents local optima without the full tree branching cost. Modelled as `BOUNDED_TOT` in the registry.

### Pattern Selection
- **Low-ambiguity task** → ReAct 1
- **Iterating on an existing draft** → ReAct 2
- **Multiple independent architectural approaches** + early decisions constrain later ones → ToT
- **Multi-step reasoning where each step reframes the next** → CoT

---

## Current Workflow Inventory

### Existing Registered Workflows

#### Autopilot Graph — `agents/orchestrator_graph.py` (+ `workflows/runtime/orchestrator_runtime.py`)

Six-node lifecycle for fixing violations across Go, Python, and TypeScript codebases.

```
ContextGatherNode → SentryNode → LogicDraftNode → StyleDraftNode → GuardNode
                                       ↑                                  ↓
                                 (retry loop) ←———— REJECTED ————————————┘
                                                     ↓ APPROVED
                                               MemorySyncNode → End
```

| Node | Agent | Mode |
|------|-------|------|
| `ContextGatherNode` | None — DB queries + file reads | Sequential |
| `SentryNode` | `sentry_agent` (Micro tier) | Single |
| `LogicDraftNode` | `fixer_agent` (Standard tier) | Fan-out via `anyio.create_task_group` |
| `StyleDraftNode` | `scribe_agent` | Fan-out |
| `GuardNode` | Deterministic CLI checks (no LLM) | Sequential |
| `MemorySyncNode` | None — DB write | Sequential |

**State:** `AutopilotState` — `language`, `target_files`, `context_violations`, `context_decisions`, `file_contents`, `sentry_tests`, `fixer_patches`, `styled_patches`, `validation_status`, `retry_count`, `max_retries`, `success`

**Reasoning mode:** ReAct-Challenge (Sentry re-thinks the violation context before drafting tests)

---

#### Managed Workflow Graph — `agents/workflow_graph.py` (+ `workflows/runtime/managed_workflow_runtime.py`)

Nine-node workflow initiated from a `WorkflowPlan` produced by `router_agent`. Controlled by `execute_agents: bool` — when `False` the graph runs as a dry-run skeleton for planning.

```
ContextGather → PlanWorkflow → Implementation → Audit → DebugOrValidation
                                    ↑                          ↓
                              (retry loop)             Documentation
                                                               ↓
                                                       ContextMapUpdate → MemoryBankSync → FinalReport → End
```

**State:** `ManagedWorkflowState` — per-stage outputs keyed by stage name, plus `execute_agents`, `retry_count`, `max_retries`

**Reasoning mode:** ReAct-Challenge

---

#### Package Audit Runtime — `workflows/runtime/package_audit_runtime.py`

Iterative audit runtime that does **not** use `pydantic-graph`. Processes packages file-by-file in bounded chunks without LLM-controlled looping.

```
for each package:
    discover_files() → chunk_files(size=5)
    for each chunk:
        read_files()          # sync, no thread pool
        analyze_chunk()       # → preloaded_audit_agent (if execute_agents=True)
deduplicate() → rank() → PackageAuditReport
```

**Models:** `ChunkFinding`, `PackageSummary`, `PackageAuditReport`

---

### Planned New Workflow Resources (29 total)

The full lifecycle planning is documented in `docs/planning/design/workflows/recommended_workflows.md`. Below is the complete map by lifecycle phase:

| Phase | Key | Profile | Reasoning | Core Agents |
|-------|-----|---------|-----------|-------------|
| **Ideation** | `idea_capture` | SMALL | ReAct | scribe, chat |
| | `research` | MEDIUM | Bounded-ToT | auditor, scribe |
| | `requirements_elicitation` | MEDIUM | Bounded-ToT | scribe, chat |
| **Architecture** | `architecture_design` | LARGE | Bounded-ToT | router, scribe, auditor |
| | `feature_design` | MEDIUM | ReAct | scribe, auditor |
| | `adr_authoring` | MEDIUM | ReAct | scribe |
| | `schema_design` | MEDIUM | Bounded-ToT | auditor, scribe |
| | `api_contract_design` | MEDIUM | ReAct | scribe, auditor |
| | `design_docs` | MEDIUM | ReAct | scribe |
| | `runbook_authoring` | SMALL | ReAct | scribe |
| | `disaster_recovery` | MEDIUM | Bounded-ToT | auditor, scribe |
| | `command_design` | SMALL | ReAct | scribe, fixer |
| | `error_logging_design` | SMALL | ReAct | scribe, auditor |
| **Setup** | `project_scaffold` | MEDIUM | ReAct | fixer, scribe |
| | `dependency_audit` | MEDIUM | ReAct | auditor |
| | `ci_setup` | MEDIUM | ReAct | scribe, auditor |
| **Development** | `implementation_planning` | MEDIUM | ReAct 2 | router, scribe |
| | `feature_implementation` | LARGE | ReAct | sentry, fixer, auditor, scribe |
| **Hardening** | `security_hardening` | LARGE | Bounded-ToT | auditor, fixer, scribe |
| | `performance_profiling` | LARGE | Bounded-ToT | auditor, fixer, scribe |
| **Documentation** | `docs_generation` | MEDIUM | ReAct | scribe |
| | `changelog_authoring` | SMALL | ReAct | scribe |
| | `onboarding_docs` | MEDIUM | ReAct | scribe |
| **Release** | `release_preparation` | MEDIUM | ReAct | scribe, auditor |
| | `deployment_validation` | MEDIUM | ReAct | auditor |
| **Maintenance** | `refactor` | LARGE | ReAct | mapper, fixer, auditor, scribe |
| | `codebase_migration` | LARGE | Bounded-ToT | mapper, fixer, auditor, scribe |
| | `code_skeptic` | LARGE | Bounded-ToT | auditor |
| | `utility_extraction` | MEDIUM | ReAct | mapper, fixer, auditor |

> Already registered: `autopilot_graph`, `managed_workflow_graph`, `package_audit`
> Already type-mapped but no dedicated `WorkflowResource` yet: `bug_fix`, `hotfix`, `refactoring`, `documentation`, `test_coverage`, `code_review`, `security_patch`, `dependency_update`

### Implementation Order

Workflows split into two groups based on agent availability.

**Group A — Ready Now** (existing agent roster: `auditor`, `scribe`, `fixer`, `router`, `mapper`,
`sentry`, `validation`, `task`, `decision`):

| Priority | Workflow | Reason |
|----------|----------|--------|
| 1 | `feature_implementation` | Highest value; uses every core group |
| 2 | `refactor` | Common task; `mapper`+`fixer`+`auditor` pipeline |
| 3 | `research` | Unblocked; Bounded-ToT on `auditor`/`scribe` |
| 4 | `security_hardening` | High-value; `auditor`+`fixer`+`scribe` |
| 5 | `performance_profiling` | Same group as security; similar structure |
| 6 | `adr_authoring`, `feature_design`, `schema_design` | Architecture tier |
| 7 | `dependency_audit`, `ci_setup` | Setup tier |
| 8 | `docs_generation`, `changelog_authoring`, `onboarding_docs` | Documentation tier |
| 9 | `release_preparation`, `deployment_validation` | Release tier |
| 10 | `codebase_migration`, `code_skeptic`, `utility_extraction` | Maintenance tier |
| 11 | `api_contract_design`, `project_scaffold`, `implementation_planning` | Remaining unblocked |

**Group B — Blocked** (missing/incomplete agents):

| Workflow | Blocker | Status |
|----------|---------|--------|
| `idea_capture` | `chat_agent` incomplete | Needs interactive discovery loop |
| `requirements_elicitation` | `chat_agent` incomplete | Same blocker |
| `architecture_design` | `diagram_agent` incomplete | Needs C4 Mermaid generation |
| `command_design` | Unclear lifecycle coupling | `fixer`+`scribe` available; coupling TBD |

---

## Workflow Infrastructure (`resources/workflows/`)

| File | Purpose |
|------|---------|
| `registry.py` | Central `WorkflowRegistry` mapping keys → `WorkflowProfile` objects |
| `profiles.py` | `WorkflowProfile` dataclass: model overrides, stage configs, retry policies |
| `selector.py` | `select_all(key, file_count)` — returns best profile for a given request |
| `models.py` | Pydantic models for workflow configuration |
| `reasoning.py` | Named reasoning patterns (`REACT_CHALLENGE`, `BOUNDED_TOT`) |
| `task_types.py` | MCP-visible task type enumeration |
| `visualization.py` | Node-style JSON for graph visualization |

The sandbox lifecycle (`ensure_workflow_sandbox` / `finalize_workflow_sandbox` / `abort_workflow_sandbox`) in `workflows/runtime/workflow_sandbox.py` handles session tracking when `execute_agents=True`.

---

## Fan-Out Pattern

`LogicDraftNode` and `StyleDraftNode` fan out across file batches in parallel:

```python
async with anyio.create_task_group() as tg:
    for batch in batches:
        tg.start_soon(worker, batch)
```

Concurrency is determined by `config_get_concurrency_for_files(file_count)` — never hardcoded.

---

## Improvement Opportunities

| Issue | Recommendation |
|-------|---------------|
| Two graph definitions (`orchestrator_graph.py`, `workflow_graph.py`) live in `agents/` but are marked deprecated in favour of `workflows/runtime/` | Move node class definitions to `workflows/` to co-locate definitions with their runtimes |
| `package_audit_runtime.py` is a plain async loop, not a `pydantic-graph` FSM | Model as a graph for consistent tracing: `DiscoverNode → ChunkNode → AnalyzeNode → AggregateNode → End` |
| `ContextGatherNode` queries the DB synchronously | Accept pre-loaded DB context as `AutopilotState` fields passed by the caller |
| 29 new `WorkflowResource` entries are planned but none are registered yet | Add in priority order above; `feature_implementation` and `refactor` first |

---

## Command Catalog Integration (Task 027)

The CLI Command Catalog provides the user-facing entry points for the workflow infrastructure.
See `docs/planning/tasks/027-commands.md`.

| CLI Command | Workflow Entry | Current State |
|-------------|---------------|---------------|
| `workflow start` | Profile-selected `WorkflowResource` via `selector.py` | Blocked on Task 026 for full implementation; interim path via `run_subagent_workflow` |
| `agent audit` | Triggers `autopilot_graph` or `package_audit` | Available now |
| `agent fix` | Triggers `autopilot_graph` (fixer path) | Available now |
| `agent validate` | Triggers `validation_agent` in `GuardNode` | Available now |
| `agent map` | Triggers `map_agent` standalone | Available now |
| `agent document` | Triggers `scribe_agent` / `task_agent` | Available now |
| `agent research` | Triggers `auditor`/`scribe` Bounded-ToT | Requires `research` workflow resource |
| `agent planning` | Triggers `router`/`scribe` ReAct 2 | Requires `implementation_planning` resource |

**`workflow start` unblocking path:**
1. Task 026 lands — implements the full profile-selected workflow runtime
2. Task 027 Phase 8 wires `workflow start` through `selector.py` → `WorkflowProfile`
3. Workflows from Group A (above) are registered one-by-one in priority order

**Agent command integration (Task 027, Phase 7):**
- Each `agent *` command routes through existing `tools/agents/*.py` MCP tools
- Returns a `task_id` for long-running work; polled via `background_task_status`
- No new command-specific MCP tools are added
