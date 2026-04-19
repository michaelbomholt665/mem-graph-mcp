# Code Review — `src/mem_graph/agents/`

**Reviewer:** GitHub Copilot  
**Package:** `src/mem_graph/agents/`
**Files reviewed:**
- `__init__.py`
- `discovery.py`
- `orchestrator_agent.py`
- `orchestrator_graph.py`
- `router_agent.py`
- `workflow_graph.py`
- `audit/__init__.py`
- `audit/audit_agent.py`
- `audit/factory.py`
- `audit/rule_injector_agent.py`
- `audit/rules/__init__.py`
- `audit/rules/base.py`
- `audit/rules/correctness.py`
- `audit/rules/go.py`
- `audit/rules/maintainability.py`
- `audit/rules/python.py`
- `audit/rules/security.py`
- `builder/__init__.py`
- `builder/agent_builder.py`
- `document/__init__.py`
- `document/decision_agent.py`
- `document/scribe_agent.py`
- `document/task_agent.py`
- `document/triage_agent.py`
- `fix/__init__.py`
- `fix/fixer_agent.py`
- `map/__init__.py`
- `map/chat_agent.py`
- `map/diagram_agent.py`
- `map/map_agent.py`
- `validate/__init__.py`
- `validate/sentry_agent.py`
- `validate/validation_agent.py`

---

## Summary

The package has a strong overall structure: typed agent inputs/outputs, clear sub-agent boundaries, deterministic orchestration helpers, and sensible use of `defer_model_check`. The highest-risk issue is an SSRF hole in the rule injector. The next tier of problems is mostly correctness and maintainability debt around hidden mutable state, blocking file I/O inside async orchestration, and weak boundary validation on file discovery.

---

## Issues

### 1. Arbitrary URL fetch in the rule injector enables SSRF — HIGH

**Location:** `audit/rule_injector_agent.py:157-187`

`rule_injector_fetch_external_rules()` accepts an `endpoint` argument from the model and performs `client.get(endpoint)`. The guard only checks whether `ctx.deps.external_api_url` is configured; it never constrains the actual request target to that configured URL.

That means a prompt-injected or misaligned model can fetch arbitrary internal or metadata endpoints instead of the intended policy service.

**Suggested fix:** Ignore the tool argument and always fetch `ctx.deps.external_api_url`, or validate the requested URL against a strict allowlist before issuing the request.

---

### 2. Multiple agents persist run state on private `RunContext` attributes — MEDIUM

**Location:**  
- `fix/fixer_agent.py:198-235`  
- `validate/sentry_agent.py:127-157`  
- `validate/validation_agent.py:214-243`  
- `document/scribe_agent.py:188-197`  
- `document/decision_agent.py:319-323`  
- `document/task_agent.py:314-316`  
- `document/triage_agent.py:318-320`  
- `map/map_agent.py:317-326`

Several agents stash accumulated output on ad-hoc `ctx._...` attributes and suppress typing with `# type: ignore[attr-defined]`. This creates hidden mutable state with no declared schema and couples behavior to the undocumented lifetime of the Pydantic AI `RunContext`.

Even if it works today, it is fragile under refactors, hard to test, and easy to break with a typo or reuse pattern.

**Suggested fix:** Move accumulators into explicit dependency fields or a typed per-run state object rather than mutating private context attributes.

---

### 3. `_read_batch()` advertises concurrent async reads but still blocks the event loop — MEDIUM

**Location:** `orchestrator_agent.py:648-682`

`_read_batch()` spawns workers with `anyio.create_task_group()`, but each worker calls `_read_single()`, which uses synchronous `Path(path).read_bytes()`. That means the task group does not provide true non-blocking I/O; a large or slow file read still blocks the loop.

This is especially misleading because the rest of the package often uses `anyio.Path(...).read_bytes()` correctly.

**Suggested fix:** Make `_read_single()` async and use `await anyio.Path(path).read_bytes()`.

---

### 4. File discovery trusts raw `package_path` / extension input without boundary checks — MEDIUM

**Location:**  
- `orchestrator_agent.py:700-705`  
- `audit/audit_agent.py:210-221`  
- `map/map_agent.py:227-238`  
- `document/decision_agent.py:230-244`

The various `list_files()` helpers build recursive glob patterns directly from dependency values. There is no normalization or check that `package_path` stays within the repository root, and `decision_agent.list_files()` even exposes the extension as a tool argument.

If these deps ever come from a user-controlled request path or an indirectly model-selected target, the agents can enumerate arbitrary filesystem locations rather than just the intended project tree.

**Suggested fix:** Resolve the base path, enforce that it is under an approved root, and constrain extensions to an allowlist.

---

### 5. Deterministic orchestration mutates caller-owned dependency state in place — MEDIUM

**Location:** `orchestrator_agent.py:296-349`

`run_orchestrator_batches()` clears and repopulates `deps.batch_results` and `deps.aggregate` on the passed-in dependency object. That makes the helper non-reentrant and easy to misuse if the same dependency instance is reused across runs or shared by higher-level code.

This is not a thread leak, but it is unnecessary shared-state coupling in code that otherwise aims to be deterministic.

**Suggested fix:** Build fresh local accumulators inside `run_orchestrator_batches()` and return them in the `OrchestratorReport` instead of mutating the input object.

---

### 6. Broad exception swallowing hides operational bugs and silently drops context — LOW

**Location:**  
- `workflow_graph.py:107,133,187,213`  
- `orchestrator_graph.py:651-739, 767-785, 895`  
- `orchestrator_agent.py:367-437`

Several paths catch broad exceptions and convert them into empty context, failed batches, or warning logs. In particular, the `_state_query_*()` helpers in `orchestrator_graph.py` silently return empty results on any failure, which can make the graph run look valid while losing decision/violation grounding.

This is sometimes intentional for resiliency, but today it also masks ordinary programming or integration bugs.

**Suggested fix:** Narrow exception handling where possible and log full tracebacks for unexpected failures.

---

## Positive Observations

- The package consistently uses typed dataclass dependencies and typed result models, which makes agent contracts readable.
- `defer_model_check` is applied broadly, which is useful for tests and cold-start safety.
- The split between standalone agents and deterministic orchestration helpers is clear, even where some implementation details still need cleanup.
- Most file-reading helpers already use `anyio.Path(...).read_bytes()`, so the blocking path in `orchestrator_agent.py` looks fixable without a wider redesign.

---

## Verdict

**Request changes.** The SSRF issue should be fixed before exposing the rule injector in a server workflow. The remaining issues are mostly correctness and boundary-hardening work, but they affect reliability enough that I would address them before expanding these agents' use in production FastMCP flows.
