# 040: Pydantic AI Advanced Concepts Analysis

Why
- `docs/planning/design/agents/13-pydantic-ai-advanced-concepts.md` documents message history, advanced tool behavior, and toolsets as important Pydantic AI primitives.
- These concepts affect how `mem_graph` should preserve conversational state, expose tools dynamically, and compose reusable tool groups.

---

## Current State

Observed codebase facts:

### 1. Message History
- No use of `message_history=` was found under `src/mem_graph`.
- No use of `result.all_messages()` or `result.new_messages()` was found under `src/mem_graph`.
- No use of `ModelMessagesTypeAdapter` was found under `src/mem_graph`.
- Current multi-step workflows rely on typed Python state (`pydantic-graph`, dependency objects, persisted domain models), not serialized model message history.

Implication:
- Agent continuity is currently application-managed, not conversation-history-managed.
- That is a valid design choice for deterministic workflows, but it means `mem_graph` does not yet support resumable conversational context at the Pydantic AI message layer.

### 2. Streaming Execution
- `run_stream(...)` is already used in tool-facing entrypoints:
  - `src/mem_graph/tools/agents/audit.py`
  - `src/mem_graph/tools/agents/map.py`
  - `src/mem_graph/tools/agents/triage.py`
  - `src/mem_graph/tools/work/decisions.py`
  - `src/mem_graph/tools/work/tasks.py`
- No use of `run_stream_events(...)` was found.
- No use of `agent.iter()` was found.

Implication:
- The codebase already uses final-result streaming where useful, but not event-level tracing or turn-by-turn manual stepping.

### 3. Advanced Tool Features
- No tool `prepare=` usage was found.
- No `ToolReturn` usage was found.
- No `ModelRetry` usage was found.
- No `Tool.from_schema(...)` usage was found.

Implication:
- Tool exposure is currently static.
- Tool failures and argument correction rely on existing validation or plain exceptions rather than explicit model self-correction hooks.
- External schema-driven tool registration is not part of the current architecture.

### 4. Toolsets
- No `FunctionToolset` usage was found.
- No `toolsets=[...]` registration was found.
- Tool composition is currently achieved through direct `@agent.tool` registration and module-local prompt instructions.

Implication:
- Related tools are grouped by file/module convention rather than via reusable Pydantic AI toolset objects.
- This mirrors the earlier capability gap: the codebase works, but cross-cutting tool composition is not yet formalized.

---

## Where These Concepts Fit

### A. Message History for User-Facing Conversational Flows

Candidate areas:
- `src/mem_graph/agents/map/chat_agent.py`
- any future interactive memory assistant or long-running session workflow

Why:
- `chat_agent` is the clearest candidate for conversational continuity.
- Message history would be useful only where the product truly wants turn-by-turn memory at the model layer rather than deterministic state reconstruction from the graph.

Recommended boundary:
- use message-history persistence only for conversational UX
- do not retrofit message history into deterministic workflow graphs where typed state is the canonical source of truth

### B. Dynamic Tool Availability via `prepare`

Candidate areas:
- routing/orchestration tools whose availability should depend on workflow mode or loaded context
- audit/fix/validation tools that should disappear when operating in preloaded mode

Why:
- Several agents embed tool-usage restrictions in prompt text today.
- If the constraint is hard, prompt text is weaker than actually hiding unavailable tools.

Recommended boundary:
- use `prepare` when a tool must be impossible rather than merely discouraged
- keep prompt-only guidance for soft preferences

### C. `ModelRetry` at System Boundaries

Candidate areas:
- tools that accept structured user-derived arguments
- any tool where bad model arguments are common and correctable

Why:
- Current workflows appear to trust the model/tool contract more than they enforce a correction loop.
- `ModelRetry` is useful when the model can realistically fix the call from the error message.

Recommended boundary:
- use `ModelRetry` only for recoverable argument mistakes
- do not use it to mask true business-logic failures or missing external resources

### D. Toolsets for Reusable Tool Families

Candidate areas:
- filesystem-style tool families shared across audit/map/task flows
- graph query tool families
- documentation/style tool families

Why:
- The codebase repeatedly defines related tool clusters with matching prompt guidance.
- Toolsets would give one representation for grouped tools plus their shared usage instructions.

Recommended boundary:
- adopt toolsets only where the same cluster would otherwise be duplicated across agents
- do not replace clear local tool definitions with a generic toolset unless reuse is real

---

## Recommended Work

1. Add a focused analysis task for `chat_agent` message-history persistence.
   - Decide whether conversational continuity belongs in message history, graph state, or both.
2. Audit preloaded-mode agents for hard tool-gating opportunities using `prepare`.
   - If a tool must not be callable, hide it instead of only warning in prompt text.
3. Identify high-value tool boundaries for `ModelRetry`.
   - Limit this to recoverable input-shape errors.
4. Prototype one reusable toolset for a genuinely shared tool family.
   - Start small; avoid a broad migration without repeated usage.
5. Defer `run_stream_events()` and `iter()` until a concrete debugging or UI need exists.
   - No evidence yet that event-level complexity would pay for itself.

---

## Verification Notes

Grounded observations used for this task:
- `run_stream(...)` usage was found in several tool entrypoints.
- No `message_history`, `all_messages()`, `new_messages()`, or `ModelMessagesTypeAdapter` usage was found under `src/mem_graph`.
- No `prepare=`, `ToolReturn`, `ModelRetry`, `Tool.from_schema(...)`, `FunctionToolset`, or `toolsets=` usage was found under `src/mem_graph`.
