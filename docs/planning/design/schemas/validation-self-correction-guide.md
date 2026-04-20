# Validation Self-Correction Guide

This repository separates graph-facing models from agent I/O schemas so Pydantic validation can do useful corrective work instead of only rejecting malformed output.

## What Lives Where

- `src/mem_graph/models/agent_outputs.py` holds shared agent output contracts used by agents, evals, workflows, and tools.
- `src/mem_graph/models/audit.py`, `work.py`, `task.py`, and `evals.py` hold graph-facing or framework-facing models.
- `src/mem_graph/models/schema_contracts.py` enforces repository rules for schema quality.
- `scripts/validate_schemas.py` provides a CLI gate for those contract checks.

The split matters because agent outputs are validation contracts, not persistence models. They need stronger descriptions and tighter unions than graph storage alone would require.

## Why Descriptions Matter

Pydantic AI retries when output validation fails. The retry prompt includes validation errors and the target schema. A weak schema gives the model almost no signal about what to repair. A strong schema tells it exactly what the field means, how precise it must be, and which values are legal.

Weak description:

```python
line_start: int
```

Strong description:

```python
line_start: int = Field(
    description=(
        "1-indexed line number where the violation begins. "
        "Use the nearest function boundary if the exact line is unknown."
    )
)
```

The strong version gives the model a recovery strategy instead of a bare type.

## Repository Contract Rules

The schema contract checker currently enforces four rules across the maintained schema surface.

1. Every field must have a non-empty `Field(description=...)`.
2. `Any` is forbidden in public schema annotations.
3. Bare `dict` or `dict[str, Any]` mappings are forbidden.
4. Enum-like fields such as `phase`, `intent`, `relationship_kind`, and `ask_user_policy` must use `Literal` or `Enum` instead of plain `str`.

Run the contract gate with:

```bash
python scripts/validate_schemas.py
```

Regression coverage lives in `tests/test_schema_contracts.py`.

## Patterns That Improve Correction

### Prefer `Literal` or `Enum` for closed sets

Use:

```python
TaskPhase = Literal["planning", "red", "green", "refactor", "audit"]
```

Instead of:

```python
phase: str
```

Closed sets give the model an explicit correction target when it invents an invalid value.

### Prefer discriminated unions to ad-hoc dict payloads

Use concrete aggregates such as `AuditAggregate`, `MapAggregate`, `DecisionAggregate`, and `GenericAggregate` rather than anonymous dictionaries. This improves both runtime safety and the quality of retry instructions when a branch is malformed.

### Prefer JSON-safe payloads when flexibility is unavoidable

If a payload truly needs to stay generic, use the shared recursive `JSONValue` alias and document the payload shape in the surrounding field description.

## Examples in This Repository

- `RouterDecision.intent` uses a closed `Literal` intent set.
- `WorkflowPlan.ask_user_policy` uses a closed `Literal` policy set.
- `OrchestratorReport.aggregate` uses typed aggregate models instead of raw dict payloads.
- `ValidationViolation.check` and `severity` use repository-specific literal contracts.

## When Adding a New Schema

1. Decide whether the model is a graph model or an agent I/O model.
2. Add full `Field(description=...)` text for every field.
3. Replace plain strings for closed domains with `Literal` or `Enum`.
4. Avoid bare dicts; prefer typed models or `dict[str, JSONValue]` only when necessary.
5. Run `python scripts/validate_schemas.py`.
6. Run `python -m pytest tests/test_schema_contracts.py -q`.

## Failure Mode to Avoid

Do not treat validation as a formatting pass. In this codebase, validation is part of the control loop. The schema itself should tell the model how to recover from an invalid output, not just what Python type will eventually be accepted.
