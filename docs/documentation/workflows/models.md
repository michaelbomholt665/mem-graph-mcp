# Workflow Data Models

> **Module:** `src/mem_graph/resources/workflows/models.py`  
> All workflow runtime objects are typed Pydantic v2 models. Pydantic validates every field at
> import time — there is no dynamic schema loading. Profile and reasoning objects are constructed
> once in `profiles.py` / `reasoning.py` and stored in module-level constants.

```mermaid
---
config:
  theme: base
  look: classic
  themeVariables:
    primaryColor: "#4338ca"
    primaryTextColor: "#ffffff"
    primaryBorderColor: "#3730a3"
    secondaryColor: "#6366f1"
    tertiaryColor: "#e0e7ff"
    lineColor: "#4338ca"
    fontFamily: "ui-monospace, monospace"
    fontSize: "13px"
    classText: "#1e1b4b"
---
classDiagram
    direction TB

    %% ── Top-level resource ──────────────────────────────────────────────
    class WorkflowResource {
        <<Pydantic BaseModel>>
        +str key
        +str display_name
        +str description
        +ProfileSize profile
        +list~str~ task_types
        +list~WorkflowStageDefinition~ stages
        +ReasoningMode reasoning_mode
        +Literal risk_level
        +str source_module
        +WorkflowSandboxPolicy sandbox_policy
        ── registry.py ──
        +key is unique in _WORKFLOW_REGISTRY
        +risk_level ∈ low · medium · high
    }

    %% ── Stage definition ────────────────────────────────────────────────
    class WorkflowStageDefinition {
        <<Pydantic BaseModel>>
        +str name
        +str description
        +str agent
        +list~str~ allowed_tools
        +list~str~ depends_on
        +list~str~ parallel_with
        +list~str~ artifacts
        ── visualization.py ──
        +depends_on drives Mermaid edge list
        +parallel_with is advisory only
    }

    %% ── Profile ─────────────────────────────────────────────────────────
    class WorkflowProfile {
        <<Pydantic BaseModel>>
        +ProfileSize size
        +str description
        +int max_stages  ge=1
        +int fan_out_limit  ge=1
        +int retry_cycles  ge=0
        +int checkpoint_frequency  ge=0
        +list~StagePolicy~ stage_policies
        +WorkflowSandboxPolicy sandbox_policy
        ── profiles.py ──
        +SMALL: max_stages=3, fan_out=1
        +MEDIUM: max_stages=6, fan_out=3
        +LARGE: max_stages=10, fan_out=6
    }

    %% ── Stage policy ────────────────────────────────────────────────────
    class StagePolicy {
        <<Pydantic BaseModel>>
        +str name
        +list~str~ allowed_agents
        +bool parallel
        +bool retry_allowed
        +int tool_budget  ge=1
        ── note ──
        +Overrides when matched by stage name
        +tool_budget enforced per-stage call
    }

    %% ── Sandbox policy ──────────────────────────────────────────────────
    class WorkflowSandboxPolicy {
        <<Pydantic BaseModel>>
        +bool enabled
        +str image
        +Literal network
        +str memory
        +str cpus
        +int exec_timeout_seconds  ge=1
        +int session_ttl_seconds  ge=1
        +bool merge_back
        +bool retain_artifacts
        ── secure defaults ──
        +network = none
        +image = python:3.14-slim
        +merge_back = False
    }

    %% ── Reasoning policy ────────────────────────────────────────────────
    class ReasoningPolicy {
        <<Pydantic BaseModel>>
        +ReasoningMode mode
        +str description
        +list~str~ required_steps
        +int tree_width  ge=0
        +int tree_depth  ge=0
        +list~str~ pruning_criteria
        +int budget_cap  ge=0
        ── reasoning.py ──
        +REACT_CHALLENGE: 4 required steps
        +BOUNDED_TOT: width=3, depth=2
        +budget_cap=0 means not applicable
    }

    %% ── Enumerations ────────────────────────────────────────────────────
    class ProfileSize {
        <<enumeration>>
        SMALL
        MEDIUM
        LARGE
    }

    class ReasoningMode {
        <<enumeration>>
        REACT_CHALLENGE
        BOUNDED_TOT
    }

    %% ── Relationships ───────────────────────────────────────────────────
    WorkflowResource "1" *-- "1..*" WorkflowStageDefinition : stages
    WorkflowResource "1" *-- "1" ProfileSize : profile
    WorkflowResource "1" *-- "1" ReasoningMode : reasoning_mode
    WorkflowResource "1" o-- "0..1" WorkflowSandboxPolicy : sandbox_policy optional

    WorkflowProfile "1" *-- "1" ProfileSize : size
    WorkflowProfile "1" *-- "0..*" StagePolicy : stage_policies
    WorkflowProfile "1" *-- "1" WorkflowSandboxPolicy : sandbox_policy default

    ReasoningPolicy "1" *-- "1" ReasoningMode : mode
```

## Inheritance & Validation Notes

- All models extend `pydantic.BaseModel` — no ORM mapping.
- `ProfileSize` and `ReasoningMode` extend `str, Enum` making them JSON-serialisable as strings.
- `WorkflowSandboxPolicy.network` is `Literal["none", "bridge"]` — only two valid values.
- `WorkflowResource.risk_level` is `Literal["low", "medium", "high"]`.
- `WorkflowResource.sandbox_policy` is optional (`None`); the profile's policy is used as fallback in `selector.py`.

## Model Instantiation Map

| Constant | Module | Type |
|----------|--------|------|
| `SMALL_PROFILE` | `profiles.py` | `WorkflowProfile` |
| `MEDIUM_PROFILE` | `profiles.py` | `WorkflowProfile` |
| `LARGE_PROFILE` | `profiles.py` | `WorkflowProfile` |
| `REACT_CHALLENGE_POLICY` | `reasoning.py` | `ReasoningPolicy` |
| `BOUNDED_TOT_POLICY` | `reasoning.py` | `ReasoningPolicy` |
| `_AUTOPILOT_WORKFLOW` | `registry.py` | `WorkflowResource` |
| `_MANAGED_WORKFLOW` | `registry.py` | `WorkflowResource` |
| `_PACKAGE_AUDIT_WORKFLOW` | `registry.py` | `WorkflowResource` |
