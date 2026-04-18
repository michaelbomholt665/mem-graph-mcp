# 017 Agent Update Plan

## Goal

Refactor the agent architecture so deterministic workflow control lives in Python / `pydantic_graph`, while LLM agents are used only for reasoning-heavy steps. Add an optional one-prompt workflow mode that can run implementation, audits/debugging, documentation, context-map updates, and memory-bank sync through managed sub-agents.

This workflow must be opt-in. The default router behavior should remain lightweight routing/classification unless the caller explicitly requests the full sub-agent workflow.

## Current Findings

- `src/mem_graph/agents/orchestrator_agent.py` still asks an LLM to follow a deterministic batching loop: list files, process each batch, then finalize. That control flow should be a pure async function or a `pydantic_graph` workflow.
- `src/mem_graph/agents/audit/audit_agent.py` has two different workflows in one prompt depending on `extra_file_context`. Split standalone audit from orchestrated/preloaded audit.
- Both orchestrator and audit use `RunContext` side-channel state (`ctx._orch_state`, `ctx._audit_state`). Mutable run accumulators should live on dependency/state objects.
- `src/mem_graph/agents/router_agent.py` repeats tier-selection rules in prompt prose even though `router_compute_tier_hint` already owns deterministic tier logic.
- `src/mem_graph/agents/orchestrator_graph.py` already has the right direction: explicit `pydantic_graph` nodes, shared typed state, deterministic routing, and LLM calls only inside nodes that need reasoning.
- `src/mem_graph/resources/personas.py` and `src/mem_graph/resources/prompts.py` should become first-class inputs to workflow-agent and agent-builder behavior instead of ad hoc prompt text scattered across agents.

## Task List

### 1. Replace LLM-Controlled Orchestrator Batching

- [ ] Add a deterministic orchestration entry point that runs the existing batch workflow without asking `orchestrator_agent` to call tools in order.
- [ ] Keep useful existing models/helpers: `OrchestratorDependencies`, `BatchResult`, `OrchestratorReport`, `_read_batch`, `_dispatch`, `_merge_*`, and `_summarise_batch_result`.
- [ ] Move batch state into explicit state/deps fields:
  - `batch_results: list[BatchResult]`
  - `aggregate: dict[str, Any]`
- [ ] Update `orchestrate_codebase` in `src/mem_graph/tools/agents/orchestrator.py` to call the deterministic orchestration entry point instead of `orchestrator_agent.run_stream(...)`.
- [ ] Replace `_dispatch` branch chains with a sub-agent registry so new built-in and project-specific helper agents can be registered without expanding `if/elif` logic.
- [ ] Keep any remaining LLM orchestrator role limited to planning/supervisory reasoning, not loop control.

### 2. Split and Harden Audit Agents

- [ ] Add `file_results: list[FileAuditResult] = field(default_factory=list)` to `AuditDependencies`.
- [ ] Replace `_get_state(ctx)` usage with `ctx.deps.file_results`.
- [ ] Split the dual-mode audit prompt into separate agents or entry points:
  - standalone audit agent with file discovery/read tools
  - orchestrated/preloaded batch audit agent with no file-list/process/finalize loop tools
- [ ] Move audit rules into focused modules instead of one large generic list:
  - base/common
  - language-specific rules such as Python/Go
  - security
  - bugs/correctness
  - smells/maintainability
  - performance, if needed later
- [ ] Add an audit-agent factory that wires persona, rules, model tier, output type, and tools consistently.
- [ ] Register specialized audit agents through the orchestrator dispatch registry, e.g. `security_audit`, `bug_audit`, `smell_audit`.

### 3. Add Agent Builder / Agent Updater

- [ ] Add an agent-builder module, likely `src/mem_graph/agents/builder/agent_builder.py`.
- [ ] Support both creating new project helper agents and updating existing ones.
- [ ] Store project-specific helper agent specs under `agents/{project_id}/`.
- [ ] Treat generated helper agents as structured, validated specs first, not arbitrary executable Python by default.
- [ ] Suggested spec fields:
  - `name`
  - `purpose`
  - `persona_key`
  - `prompt_key`
  - `recommended_model`
  - `allowed_tools`
  - `system_prompt`
  - `inputs`
  - `outputs`
  - `eval_dataset`
  - `version`
  - `last_updated`
- [ ] Validate agent specs before writing.
- [ ] Never overwrite an existing project agent without a deliberate update path.
- [ ] Add discovery/registry support so router/orchestrator can find helper agents in `agents/{project_id}/`.
- [ ] Link agent-builder behavior to `src/mem_graph/resources/personas.py` and `src/mem_graph/resources/prompts.py`:
  - choose persona via `PERSONA_REGISTRY`
  - reuse workflow prompt templates via `PROMPT_REGISTRY`
  - allow new project-agent specs to reference existing personas/prompts before adding bespoke prompt text
- [ ] Add or reserve an `AGENT_BUILDER_PERSONA` if the existing personas are not sufficient.

### 4. Connect Agent Builder to Evals and Iterative Improvement

- [ ] Inspect current eval infrastructure under `src/mem_graph/evals/`.
- [ ] Determine whether hosted Logfire datasets can be listed/fetched through the existing Logfire dataset client or whether only known dataset names can be used.
- [ ] Add eval metadata to project helper agent specs so each helper can declare which eval suite/dataset measures it.
- [ ] Add an agent-builder update mode that can:
  - read current helper-agent spec
  - read local eval results and, where possible, hosted Logfire eval/dataset results
  - identify failure patterns
  - propose prompt/persona/tool/model changes
  - update the agent spec with a versioned changelog
- [ ] Keep eval-driven updates reviewable. The builder should produce a report of proposed changes and only write changes through an explicit update operation.
- [ ] Add tests around spec validation and update decisions; avoid requiring live Logfire credentials in unit tests.

### 5. Add Optional Router-Driven Sub-Agent Workflow

- [ ] Extend router inputs with an explicit workflow mode, for example:
  - `route_only` for current default behavior
  - `subagent_workflow` for the full one-prompt workflow
- [ ] Add a structured `WorkflowPlan` output separate from the existing `RouterDecision`.
- [ ] The workflow plan should include:
  - objective
  - project id
  - target files
  - required stages
  - stage dependencies
  - model overrides
  - allowed tools per stage
  - max retries
  - ask-user policy
- [ ] Remove duplicated prompt prose for tier rules from `router_agent`; use deterministic tier/model helpers and require the router to explain only intentional overrides.
- [ ] Keep this workflow opt-in. It must not replace normal routing unless the user or tool call explicitly asks for it.

### 6. Implement Workflow Agent With `pydantic_graph`

- [ ] Add or extend a graph-based workflow engine that follows a ReAct-style loop using explicit `pydantic_graph` nodes.
- [ ] Start from the existing `orchestrator_graph.py` pattern rather than creating another prompt-driven loop.
- [ ] Suggested nodes:
  - `ContextGatherNode`
  - `PlanWorkflowNode`
  - `ImplementationNode`
  - `AuditNode`
  - `DebugOrValidationNode`
  - `DocumentationNode`
  - `ContextMapUpdateNode`
  - `MemoryBankSyncNode`
  - `FinalReportNode`
- [ ] Let the orchestrator graph start/stop sub-agents as each node completes and route to retry/debug nodes when validation fails.
- [ ] Ensure the workflow can run from one starting prompt and does not stop mid-workflow for user input except for hard blockers, destructive operations, or missing required credentials/configuration.
- [ ] Use existing filesystem tools for sub-agents that need file edits:
  - read/search/grep for read-only stages
  - read/search/grep/edit/write for implementation, documentation, and map/memory update stages where appropriate
- [ ] Wire in `src/mem_graph/resources/personas.py` and `src/mem_graph/resources/prompts.py` so workflow stages use consistent personas and prompt templates.
- [ ] Keep shared workflow state typed and explicit; do not store state on `RunContext` attributes.

### 7. Model Selection and Overrides

- [ ] Support per-stage model selection and caller-provided model overrides.
- [ ] Use strong coding/audit models by default for implementation, audit, and debugging stages:
  - `gpt-5.4 xhigh`
  - `sonnet 4.6`
- [ ] Use cheaper/faster models by default for read/classification/context stages:
  - `gpt-5.0 mini`
  - `gpt-5.4 mini`
  - Claude Haiku once the exact model id is confirmed
- [ ] Keep model identifiers configurable in `src/mem_graph/config.py` / env vars so exact provider names can change later.
- [ ] Preserve existing tier aliases where useful, but do not force all workflow stages into one tier.

### 8. Documentation and Tests

- [ ] Update docs for:
  - deterministic orchestrator batching
  - audit-agent split
  - agent-builder create/update flow
  - eval-linked agent improvement
  - optional full sub-agent workflow
  - model override behavior
- [ ] Add focused tests for:
  - orchestrator deterministic batching and aggregation
  - audit dependency accumulator behavior
  - router `route_only` vs `subagent_workflow`
  - workflow-plan validation
  - project helper-agent spec validation
  - agent-builder create/update decisions
- [ ] Keep live Logfire / hosted eval calls behind integration tests or explicit CLI commands so local unit tests remain credential-free.

## Acceptance Criteria

- The batch orchestrator no longer depends on an LLM following numbered loop instructions.
- The audit agent no longer has a single prompt with two different workflows.
- Mutable run state lives in typed dependencies/state, not hidden `RunContext` attributes.
- Router can optionally produce a full workflow plan from one prompt, while default routing remains unchanged.
- The full workflow runs through `pydantic_graph` nodes and can manage sub-agents through implementation, audit/debugging, docs, context-map update, and memory-bank sync.
- Project-specific helper agents can be created and updated under `agents/{project_id}/`.
- Agent-builder specs tie into personas, prompt templates, model selection, allowed tools, and eval metadata.
- Evals can be used to improve helper agents over time, with hosted Logfire support investigated and local tests not depending on live credentials.
