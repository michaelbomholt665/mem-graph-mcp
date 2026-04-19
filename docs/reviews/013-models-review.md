# Code Review — `src/mem_graph/models/`

**Reviewer:** GitHub Copilot
**Resolved:** 2026-04-19
**Status:** ✅ COMPLETE — all issues fixed
**Package:** `src/mem_graph/models/`
**Files reviewed:**
- `__init__.py`
- `audit.py`
- `code.py`
- `conversation.py`
- `evals.py`
- `memory.py`
- `project.py`
- `task.py`
- `work.py`

---

## Summary

The models package is mostly clean: it is typed, readable, and uses Pydantic consistently. The main issues are contract drift and validation gaps rather than outright bugs. The most important one is in the memory model, where the declared scope vocabulary can represent backend-scoped memory but the model itself lacks a way to identify a backend.

---

## Issues

### 1. `MemoryModel` can express backend scope without a backend identifier — MEDIUM

**Location:** `memory.py:37-80`

`MemoryScope` includes `BACKEND`, but `MemoryModel` only carries `project_id`. That means the model can claim `"scope": "backend"` without carrying the data needed to identify which backend the memory belongs to.

This is a schema/contract mismatch rather than a runtime crash, but it makes backend-scoped memory ambiguous and easy to misuse.

**Suggested fix:** Add `backend_id: str | None` (with clear scope rules), or remove/rename the backend scope until the model can represent it fully.

---

### 2. `ConversationMessage.role` is an unconstrained string even though the API documents a closed set of roles — MEDIUM

**Location:** `conversation.py:16-24`

The field description says `user | assistant | system | tool`, but the type is just `str`. That weakens both validation and generated schema quality: invalid roles pass model validation and downstream code has to trust callers.

**Suggested fix:** Use a `Literal[...]` or small enum for message roles.

---

### 3. `AuditFinding` does not validate line range invariants — LOW

**Location:** `audit.py:112-120`

`line_start` and `line_end` are plain integers with no positivity or ordering checks. The model therefore accepts impossible spans such as `line_start=0`, `line_end=-5`, or `line_start > line_end`.

Because these values drive reports and violation linking, bad spans would silently propagate.

**Suggested fix:** Add `ge=1` constraints and a model validator enforcing `line_end >= line_start`.

---

### 4. `TaskProgress` fields can drift out of sync because there are no invariants on totals or percentages — LOW

**Location:** `task.py:25-33`

`current`, `total`, and `percentage` are all unconstrained. The model allows `total=0`, negative counts, or `percentage=500`, and it does not guarantee that `percentage` matches `current / total`.

If upstream code miscomputes progress once, the API will serialize inconsistent progress data without complaint.

**Suggested fix:** Add basic bounds (`current >= 0`, `total >= 1`, `0 <= percentage <= 100`) and derive `percentage` from counts in one place.

---

### 5. Recall-result models are much less explicit than the rest of the package — LOW

**Location:** `conversation.py:40-64`

`MemoryItem` uses bare `str` fields for `kind` and `scope`, even though the package already defines `MemoryKind` and `MemoryScope`. That makes the recall API weaker and less self-documenting than the graph-facing models.

**Suggested fix:** Reuse the existing enums where possible, or at least document why recall results intentionally use looser types.

---

## Positive Observations

- The package is consistently typed and avoids large “god models”.
- Enum use is generally good, especially in `audit.py`, `memory.py`, `project.py`, and `work.py`.
- `AuditReport` exposes useful derived properties (`all_findings`, `has_blockers`) without bloating the stored model shape.
- The eval models in `evals.py` are clear and compose well with the runner/reporting code.

---

## Verdict

**Approve with comments.** The models are in decent shape, but I would tighten the memory and conversation contracts and add a small amount of validation before treating these schemas as stable long-term public interfaces.
