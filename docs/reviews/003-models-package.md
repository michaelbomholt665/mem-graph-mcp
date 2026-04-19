# Code Review: `src/mem_graph/models/`

**Reviewed:** 2026-04-14
**Scope:** `audit.py`, `code.py`, `conversation.py`, `evals.py`, `memory.py`, `project.py`, `task.py`, `work.py`

---

## Summary

The models package provides well-typed Pydantic v2 contracts for the entire MCP surface — agents, tools, and graph I/O. Field descriptions are consistently used, enums are `str, Enum` for JSON compatibility, and UUIDv7 IDs are correctly documented throughout. (Note: Detailed validation gaps for roles and line ranges are now covered in 013-models-review.md).

---

## Critical Issues

_None._

---

## Suggestions

| # | File | Line | Suggestion | Category |
|---|------|------|------------|----------|
| 1 | `task.py` | ~40 | **`task_id` uses `uuid4().hex` instead of the project-standard `id_generate_v7()`.** Every other node model documents UUIDv7 as the ID convention (`ids.py`). `uuid4().hex` also strips hyphens, producing a 32-char string inconsistent with the 36-char format expected by graph queries that pattern-match on `id`. Replace with `default_factory=id_generate_v7`. | Correctness |
| 2 | `memory.py` | ~85 | **`NoteModel.kind` is an unvalidated `str`.** Other kind-type fields use enums (`MemoryKind`, `TaskStatus`) but `NoteModel.kind` accepts any string. This creates inconsistent filtering in graph queries. Consider an `Enum` or at minimum a validator that normalises casing. | Maintainability |
| 3 | `task.py` + `work.py` | top | **`TaskStatus` enum name collision.** `models/task.py` defines `TaskStatus` for background task lifecycle (`QUEUED`, `RUNNING`, `COMPLETED`, …) while `models/work.py` defines another `TaskStatus` for TDD phases (`PLANNING`, `RED`, `GREEN`, …). Any import that does `from ... import TaskStatus` will shadow one with the other. Rename the background task enum to `BackgroundTaskStatus`. | Maintainability |
| 4 | `audit.py` | ~75 | **`AuditFinding.fingerprint` is `str | None` but treated as always populated by `violation_writer`.** If `FingerprintService` is not run before writing (or fails), `None` fingerprints will cause duplicate violations in the graph. Mark the field as required once fingerprinting is mandatory, or add a pre-save assert in the violation writer. | Correctness |
| 5 | `evals.py` | ~30 | **`EvalCase.runs: int = Field(default=3, ge=1, le=10)` caps at 10.** This limit is enforced on deserialization but not documented in the public API surface. If it is intentional for cost control, add a comment explaining the rationale. If it is not intended as a permanent cap, remove the `le=10` constraint to avoid silent truncation when loading eval suites with higher run counts. | Maintainability |

---

## What Looks Good

- **Consistent use of `str, Enum`** — All enums are `str` subclasses, which means they serialise cleanly to JSON without `.value` calls.
- **`MemoryModel.confidence` bounds** — `ge=0.0, le=1.0` validated at the model level.
- **`AuditStats.by_severity` dict** — Using a flat `dict[str, int]` keyed by severity value avoids needing a nested model and is straightforward to aggregate across batches.
- **`DecisionModel.alternatives: list[str]`** — Recording rejected alternatives at model level is good domain design; enables richer drift analysis.
- **`EvalCaseResult`** — Clear separation of `pass_rate` vs `average_score` in the eval result model correctly handles the "passing threshold may differ from mean score" distinction.
- **`BatchFileContent.truncated` flag** — Explicit boolean for truncation rather than relying on content length heuristics.
- **All models use `from __future__ import annotations`** — Correct for forward-reference compatibility with Pydantic v2.

---

## Verdict

**Request Changes (minor)** — No critical issues. The `uuid4` / `id_generate_v7` inconsistency and `TaskStatus` name collision should be fixed before the service goes to production since both affect correctness of graph queries and Python imports.
