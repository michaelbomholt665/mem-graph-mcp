# Code Review — `src/mem_graph/tools/`

**Reviewer:** GitHub Copilot  
**Package:** `src/mem_graph/tools/`
**Files reviewed:**
- `__init__.py`
- `agents/audit.py`
- `agents/diagrams.py`
- `agents/map.py`
- `agents/orchestrator.py`
- `agents/triage.py`
- `background/progress.py`
- `background/task_status.py`
- `code/parser.py`
- `confirmations.py`
- `filesystem/filesystem.py`
- `filesystem/status.py`
- `filesystem/tree.py`
- `graph/graph_queries.py`
- `graph/resources.py`
- `integrations/jina.py`
- `memory/conversation.py`
- `memory/memory.py`
- `memory/notes.py`
- `work/decisions.py`
- `work/projects.py`
- `work/tasks.py`
- `work/violations.py`

---

## Summary

This folder contains most of the server's public MCP surface, so small contract mistakes matter a lot here. I found one clear data-shape bug in `decision_search`, a few safety problems around destructive/file-system tools, and a couple of places where invalid input or unavailable confirmation widens scope or proceeds with destructive behavior instead of failing closed.

---

## Issues

### 1. `decision_search()` returns the wrong fields under `status` and `impact` — MEDIUM

**Location:** `work/decisions.py:252-260`

The query returns:

```python
RETURN d.id, d.title, d.rationale, d.status, d.impact, p.id AS project_id, distance
```

but the response mapping does:

```python
"status": r[2],
"impact": r[3],
```

So callers receive the decision rationale string in `status`, and the actual status in `impact`. That corrupts the public tool contract and will mislead any UI or agent that trusts these keys.

**Suggested fix:** Map `status` to `r[3]` and `impact` to `r[4]`.

---

### 2. Destructive filesystem tools bypass the repo’s own confirmation helper — MEDIUM

**Location:** `filesystem/filesystem.py:172-251`, `confirmations.py:26-62`

`file_write`, `file_edit`, and `file_delete` mutate the server filesystem immediately. The repository already has a `require_confirmation()` helper that declines destructive actions in non-interactive environments, but nothing in the filesystem tools calls it.

That leaves the highest-risk tool namespace without the safety hook the repo appears to intend.

**Suggested fix:** Route destructive filesystem tools through `require_confirmation()` or an equivalent FastMCP elicitation path before writes/deletes proceed.

---

### 3. Filesystem tools are not root-bounded and accept arbitrary absolute paths — MEDIUM

**Location:** `filesystem/filesystem.py:44-51`, `79-88`, `172-180`, `196-205`, `234-243`

The filesystem tools describe absolute paths as input and then operate on whatever path the caller provides. There is no configured root, no containment check, and no symlink guard on the direct read/write/edit/delete surface.

Given that these are MCP-exposed tools, this means any activated client can read or mutate files outside the repository boundary as long as the server process can reach them.

**Suggested fix:** Enforce a configured allowlisted root (or roots) and reject resolved paths that escape it.

---

### 4. `get_file_violations()` can escape the chosen root and then crash on out-of-root files — MEDIUM

**Location:** `filesystem/status.py:276-288`, `110-117`

For relative paths, the tool does:

```python
resolved_path = (root / file_path).resolve()
```

but never verifies that the resolved file is still under `root`. If the resolved file exists outside the root, `load_file_status_map()` later calls `path.relative_to(root)` in `_init_statuses()`, which raises `ValueError`. That turns a crafted path like `../../outside.py` into an avoidable server error instead of a clean rejection.

**Suggested fix:** After resolving, reject any path that is not contained by `root` before calling `load_file_status_map()`.

---

### 5. `memory_manage()` proceeds with expiry when confirmation is unavailable — MEDIUM

**Location:** `memory/memory.py:113-138`

The docstring and module header say expiry should use `ctx.elicit()` for confirmation, but the implementation only attempts confirmation on a best-effort basis. If elicitation raises any exception, it logs at debug level and expires the memory anyway:

```python
except Exception as exc:
    logger.debug(
        "Elicitation unavailable, proceeding without confirmation: %s", exc
    )
```

That is fail-open behavior on a destructive path.

**Suggested fix:** Treat confirmation transport failures as a blocked destructive action, not implicit approval.

---

### 6. Invalid graph node-type filters silently widen to “all types” — LOW

**Location:** `graph/graph_queries.py:109-119`

`_normalize_node_types()` drops unrecognized values and, if none survive, falls back to `list(_NODE_LOADERS)`. So a typo in `node_types` does not fail or return an empty set; it broadens the request to the full graph snapshot/search set.

That is surprising behavior for a filtering API and can leak more data or do more work than the caller intended.

**Suggested fix:** Reject unknown node types explicitly and return a validation-style error.

---

### 7. File read/grep paths load whole files into memory with no size guard — LOW

**Location:** `filesystem/filesystem.py:53-57`, `151-163`

`file_read()` reads the entire file before slicing lines, and `_grep_file()` reads the entire file before scanning. On very large files, these tools can consume far more memory than the caller expects.

This is especially awkward because other parts of the repo already talk about bounded file operations and max-size protections.

**Suggested fix:** Check file size first and reject or truncate files above a defined threshold.

---

### 8. `generate_diagram()` silently ignores invalid `diagram_type` values — LOW

**Location:** `agents/diagrams.py:41-47`

An invalid `diagram_type` is only logged:

```python
except ValueError:
    logger.warning("Invalid diagram type '%s': Agent will infer type.", diagram_type)
```

The tool then proceeds as if the user never asked for a specific type. That makes malformed input look successful and hides request-shape problems from callers.

**Suggested fix:** Return a validation error that lists the supported diagram types.

---

## Positive Observations

- The tool modules consistently use bounded `Field()` constraints for many numeric inputs.
- `filesystem/tree.py` correctly skips symlinks during recursive tree construction.
- `work/tasks.py:_query_linked()` validates dynamic identifiers before interpolating them into Cypher.
- `graph/graph_queries.py` keeps graph depth and node count bounded, which is good defensive design for dashboard-facing tools.

---

## Verdict

**Request changes.** The folder is structurally solid, but the public tool layer still has a few contract and safety issues that should be fixed before these tools are treated as a stable production MCP surface.
