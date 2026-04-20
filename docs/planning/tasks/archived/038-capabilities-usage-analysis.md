# 038: Capabilities Usage Analysis

Why
- `docs/planning/design/agents/10-capabilities.md` defines `AbstractCapability` as the preferred extension mechanism when tools, instructions, model settings, and lifecycle hooks belong to one reusable concern.
- The current codebase wires those concerns directly into each `Agent(...)` definition instead of bundling them as capabilities.

---

## Current State

Observed codebase facts:
- No direct usage of `pydantic_ai.capabilities.AbstractCapability` exists under `src/mem_graph`.
- No agent is constructed with `capabilities=[...]`.
- The agent layer now uses `@agent.instructions` decorators for runtime instructions in:
  - `src/mem_graph/agents/audit/audit_agent.py`
  - `src/mem_graph/agents/audit/rule_injector_agent.py`
  - `src/mem_graph/agents/builder/agent_builder.py`
  - `src/mem_graph/agents/document/decision_agent.py`
  - `src/mem_graph/agents/document/scribe_agent.py`
  - `src/mem_graph/agents/document/task_agent.py`
  - `src/mem_graph/agents/document/triage_agent.py`
  - `src/mem_graph/agents/fix/fixer_agent.py`
  - `src/mem_graph/agents/map/chat_agent.py`
  - `src/mem_graph/agents/map/map_agent.py`
  - `src/mem_graph/agents/orchestrator_agent.py`
  - `src/mem_graph/agents/router_agent.py`
  - `src/mem_graph/agents/validate/sentry_agent.py`
  - `src/mem_graph/agents/validate/validation_agent.py`
- Cross-cutting behavior is duplicated at the agent-definition layer rather than abstracted:
  - persona instructions are fetched per module
  - reasoning-mode guidance is injected per module
  - tool allow-lists are rendered into prompt text in several specialist agents
  - model settings are configured per agent constructor

This means the current design is functional but not capability-oriented.

---

## Where Capabilities Fit

### 1. Audit Capability

Candidate files:
- `src/mem_graph/agents/audit/audit_agent.py`
- `src/mem_graph/agents/audit/rule_injector_agent.py`
- `src/mem_graph/workflows/runtime/package_audit_runtime.py`

Why:
- The audit domain combines multiple related concerns: auditor persona instructions, audit rules, audit-specific tools, and run-level observability.
- `audit_agent` and `rule_injector_agent` are separate today, but the extension boundary is the audit concern, not just one tool at a time.

Capability responsibilities:
- provide shared audit instructions
- expose audit toolset(s)
- centralize audit logging hooks
- optionally attach provider-specific audit model settings

### 2. Reasoning Strategy Capability

Candidate files:
- `src/mem_graph/agents/audit/audit_agent.py`
- `src/mem_graph/agents/document/decision_agent.py`
- `src/mem_graph/agents/document/task_agent.py`
- `src/mem_graph/agents/document/triage_agent.py`
- `src/mem_graph/agents/fix/fixer_agent.py`
- `src/mem_graph/agents/map/map_agent.py`
- `src/mem_graph/agents/router_agent.py`
- `src/mem_graph/agents/validate/sentry_agent.py`
- `src/mem_graph/agents/validate/validation_agent.py`

Why:
- `reasoning_mode` prompt injection is repeated across many agents.
- That is a cross-cutting execution policy, not agent-specific business logic.

Capability responsibilities:
- append reasoning instructions when `deps.reasoning_mode` is set
- keep reasoning-mode formatting consistent across agents
- expose lifecycle hooks for reasoning telemetry if needed later

### 3. Observability / Usage Tracking Capability

Candidate files:
- `src/mem_graph/agents/orchestrator_agent.py`
- `src/mem_graph/agents/orchestrator_graph.py`
- `src/mem_graph/agents/workflow_graph.py`
- `src/mem_graph/tools/agents/orchestrator.py`

Why:
- The multi-agent codebase performs many nested `agent.run(...)` calls.
- No `RunUsage` sharing or capability-level usage hooks were found.
- The design doc explicitly calls out lifecycle hooks as a capability use case.

Capability responsibilities:
- start/end run tracking
- token/usage aggregation hooks
- shared telemetry fields for delegated runs
- centralized tool error logging

### 4. Provider Adaptation Capability

Candidate files:
- `src/mem_graph/config.py`
- `src/mem_graph/agents/*`

Why:
- Model tier and stage selection already exist, but provider-aware prompt/tool adaptation does not.
- The design doc calls provider adaptation a first-class capability use case.

Capability responsibilities:
- adjust instructions for backend/provider quirks
- disable brittle tool patterns for weaker models
- attach provider-specific model settings without scattering conditionals across agents

---

## What Should Not Become a Capability Yet

Do not introduce capabilities for single-use, file-local behavior.

Examples:
- one-off prompt strings only used by a single agent
- graph node transition logic in `orchestrator_graph.py` or `workflow_graph.py`
- plain constructor wiring where there is no repeated cross-agent concern

A capability should replace repetition or define a real extension boundary. If it only wraps one module’s private behavior, it is not earning its existence.

---

## Recommended Follow-up

1. Start with a `ReasoningStrategyCapability` proof of concept.
   - Highest repetition
   - Lowest behavior risk
   - Clear before/after diff
2. Add a separate `UsageTrackingCapability` only after deciding on a canonical usage aggregation model.
3. Consider an `AuditCapability` once audit tool composition stabilizes.
4. Do not introduce a broad “everything capability.” Keep boundaries aligned with one concern each.

---

## Verification Notes

Grounded observations used for this task:
- `AbstractCapability` and `capabilities=` were not found under `src/mem_graph`.
- Delegated and standalone agent runs are present across orchestrator and workflow modules.
- `@agent.instructions` is now the prompt pattern in the 14 planned agent modules.
