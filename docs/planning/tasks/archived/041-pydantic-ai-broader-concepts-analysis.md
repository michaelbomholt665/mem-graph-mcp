# 041: Pydantic AI Broader Concepts Analysis

Why
- `docs/planning/design/agents/14-pydantic-ai-broader-concepts.md` covers the execution, safety, observability, dependency, and testing primitives that shape a reliable Pydantic AI system.
- `mem_graph` already uses some of these concepts heavily and leaves others mostly unused; documenting that split helps identify the next meaningful improvements.

---

## Current State

Observed codebase facts:

### 1. Dependency Injection & Typed Agents
- Typed dependency injection is already a core pattern in the agent layer.
- Agent modules define dependency dataclasses and pass them through `RunContext[...]`-aware tools and instruction builders.
- Tests such as:
  - `tests/test_audit.py`
  - `tests/test_decision_agent.py`
  - `tests/test_map_agent.py`
  - `tests/test_task_agent.py`
  - `tests/test_triage_agent.py`
  verify agent dependency injection with overridden models.

Implication:
- This part of the design doc is already aligned with current architecture.

### 2. Execution Modes
- `agent.run()` is used widely across the codebase.
- `run_stream(...)` is used in several tool entrypoints.
- No `run_stream_events(...)` usage was found.
- No `agent.iter()` usage was found.

Implication:
- The system uses the high-level execution APIs, but not the lower-level audit/debug execution surfaces.

### 3. Operational Safeguards
- Typed `ModelSettings` is used in `src/mem_graph/config.py` via `config_model_settings(...)`.
- Many agent constructors consume model settings built from persona configuration.
- No `UsageLimits` usage was found under `src/mem_graph`.

Implication:
- Model configuration exists, but cost/runaway safeguards are not yet expressed through Pydantic AI `UsageLimits`.

### 4. Observability
- Native Pydantic AI Logfire instrumentation is enabled in `src/mem_graph/observability/logfire_setup.py` via `logfire.instrument_pydantic_ai(...)`.
- Tests in `tests/test_logfire_setup.py` verify that instrumentation call.

Implication:
- The project already adopted the recommended observability hook.
- The main remaining gap is not instrumentation presence, but how much execution metadata is propagated into it consistently.

### 5. Testing Infrastructure
- `TestModel` is used in multiple agent tests and diagram-agent tests.
- `agent.override(model=...)` is used across tests.
- No `FunctionModel` usage was found.

Implication:
- The codebase already uses the recommended lightweight testing pattern for agent logic.
- More advanced model-behavior simulation via `FunctionModel` is not yet part of the suite.

### 6. Structured Output & Multimodal Inputs
- Structured output is already central: agent modules declare typed output models and tests depend on them.
- No direct use of multimodal request classes (`Image`, `Audio`, `Video`, `Document`) was found.
- No explicit `max_result_retries` usage was found.

Implication:
- Structured outputs are mature.
- Multimodal support is not part of the current product surface.
- Retry policy relies on framework defaults rather than explicit per-agent tuning.

---

## Where Improvements Fit

### A. Usage Limits at Orchestration Boundaries

Candidate areas:
- `src/mem_graph/tools/agents/orchestrator.py`
- graph/runtime entrypoints that can trigger multiple nested agent calls

Why:
- These are the highest-risk paths for unbounded requests and token usage.
- If the system adds unified usage tracking, usage limits should sit at the same boundary.

Recommended boundary:
- define usage limits at job/task entrypoints
- propagate them consistently through delegated runs

### B. Event-Level Streaming for Debugging, Not Default Execution

Candidate areas:
- workflow debugging surfaces
- observability-heavy development tools

Why:
- `run_stream_events()` is useful when diagnosing tool-call ordering, retries, or tool/model churn.
- There is no evidence it is needed for normal production flows yet.

Recommended boundary:
- reserve event streaming for debugging or developer tooling
- do not complicate standard user flows without a concrete need

### C. `FunctionModel` for High-Fidelity Workflow Tests

Candidate areas:
- graph/orchestrator workflow tests
- multi-turn tool-calling tests where `TestModel` is too static

Why:
- The current suite verifies injection and output shape well.
- More complex orchestration behavior may benefit from programmable model responses.

Recommended boundary:
- use `FunctionModel` only where deterministic scripted model behavior is required to test branching or retries
- keep `TestModel` as the default for simpler agent tests

### D. Explicit Retry and Safety Policy

Candidate areas:
- expensive or deeply nested orchestration flows
- agents whose outputs are costly to repair after invalid structured responses

Why:
- The codebase currently relies more on good prompts and typed outputs than on explicit execution ceilings.
- A documented policy for `UsageLimits` and explicit retry settings would make operational behavior more predictable.

---

## Recommended Work

1. Add `UsageLimits` analysis or implementation work at orchestration entrypoints.
   - Start where one user request can trigger multiple nested agent runs.
2. Keep `ModelSettings` centralized in config-driven helpers.
   - Avoid scattering provider settings ad hoc across modules.
3. Introduce `FunctionModel` only for workflow tests that need scripted multi-turn/tool-call behavior.
   - Do not replace simpler `TestModel` coverage without cause.
4. Evaluate whether any production debugging surface truly needs `run_stream_events()`.
   - If not, keep the simpler `run()` and `run_stream()` split.
5. Do not add multimodal abstractions until the product actually accepts multimodal inputs.
   - No current evidence justifies that complexity.

---

## Verification Notes

Grounded observations used for this task:
- `ModelSettings` usage is present in `src/mem_graph/config.py`.
- `logfire.instrument_pydantic_ai(...)` is present in `src/mem_graph/observability/logfire_setup.py` and tested.
- `TestModel` and `agent.override(...)` are used across multiple tests.
- No `UsageLimits`, `FunctionModel`, `run_stream_events(...)`, `agent.iter()`, multimodal request classes, or explicit `max_result_retries` usage was found under `src/mem_graph` and `tests`.
