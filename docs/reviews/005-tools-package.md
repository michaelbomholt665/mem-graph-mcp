# Code Review: `src/mem_graph/tools/`

**Reviewed:** 2026-04-14
**Scope:** `agents/audit.py`, `agents/diagrams.py`, `agents/map.py`, `agents/orchestrator.py`, `agents/triage.py`, `background/`, `confirmations.py`, `filesystem/filesystem.py`, `filesystem/status.py`, `filesystem/tree.py`, `graph/graph_queries.py`, `integrations/jina.py`, `memory/conversation.py`, `memory/memory.py`, `memory/notes.py`, `work/decisions.py`, `work/projects.py`, `work/tasks.py`, `work/violations.py`

---

## Summary

The tools package is the MCP surface layer. Tool design is generally clean: progress reporting, task-queue integration, and FastMCP dependency injection are all applied consistently. The most significant concern is the unrestricted filesystem access model in `filesystem.py` — while protected by lazy-namespace activation, once activated the AI has full read/write/delete authority on every path the server process can reach. Several secondary issues are noted below.

---

## Critical Issues

| # | File | Line | Issue | Severity |
|---|------|------|-------|----------|
| 1 | `filesystem/filesystem.py` | ~35–280 | **No filesystem root containment.** `file_read`, `file_write`, `file_edit`, `file_delete`, `file_grep`, and `file_search` all accept arbitrary absolute paths with no allowlist or root-restriction check. A prompt injection in any agent session that has activated the `filesystem` namespace can read `/etc/passwd`, `/home/.../.ssh/id_rsa`, or overwrite arbitrary process-accessible files. A `MEM_GRAPH_FS_ROOT` env-var allowlist (defaulting to the project directory) should be enforced in a shared helper before every path operation. | 🔴 Critical |

---

## Suggestions

| # | File | Line | Suggestion | Category |
|---|------|------|------------|----------|
| 1 | `filesystem/filesystem.py` | ~185 | **`file_write` creates files without confirmation.** The docstring warns "Overwrites existing files without confirmation", but unlike destructive `file_delete`, no confirmation modal is shown via `require_confirmation`. For existing files at least, the `confirmations.require_confirmation` pattern used elsewhere should be applied. | Security |
| 2 | `agents/audit.py` | ~38 | **`_SKILLS_PATH` uses `os.getcwd()`.** If the server is started from a different working directory, the skills file silently cannot be loaded and the audit falls back to defaults without logging a warning. Use `Path(__file__).resolve().parents[3] / "skills" / "audit_agent" / "SKILL.md"` for reliability. | Correctness |
| 3 | `work/tasks.py` | ~130 | **`task_update` builds a Cypher SET clause with an f-string.** The approach `SET {", ".join(set_clauses)}` is structurally fine (the clause strings are hardcoded). However the pattern is fragile — a future contributor adding a user-supplied field name would produce a Cypher injection. Extract a validated `_build_set_clauses` helper that maps field names through an explicit allowlist. | Maintainability |
| 4 | `graph/graph_queries.py` | ~85 | **`load_node_styles()` reads from disk on every call.** The `node_styles.json` is loaded on every hit to `/dashboard/api/styles`. Add `@functools.lru_cache(maxsize=1)` or cache at module level after first read. | Performance |
| 5 | `memory/memory.py` | ~95 | **`ctx: Context = None` pattern used throughout tools.** Using `None` as default with `# type: ignore[assignment]` works at runtime via FastMCP injection but leaks the type system contract. If a tool is called outside FastMCP (tests, scripts), `ctx` is unexpectedly `None`. Use `ctx: Context | None = None` and guard with `if ctx is not None`. | Correctness |
| 6 | `confirmations.py` | ~43 | **`ConfirmationResponse.approved=False` in non-interactive mode is silent.** Tools that call `require_confirmation` in non-interactive environments receive `approved=False, reason="non_interactive"` without any log. The caller should log a warning so operators can diagnose why destructive operations are silently skipped. | Maintainability |
| 7 | `agents/audit.py` | ~100 | **Task-queue lambda captures mutable `ctx` by reference.** `runner=lambda reporter: _audit_package_worker(..., ctx=ctx)` captures `ctx` at enqueue time. If `ctx` represents a connection object that may be invalidated on disconnect, this could cause spurious errors in the background worker. Prefer capturing only serializable state (session ID, parameters) in the lambda. | Correctness |
| 8 | `tools/work/tasks.py` | ~30 | **`task_create` priority validation.** The parameter description lists `low \| normal \| high \| critical` but the field is an unvalidated `str`. The graph schema may enforce this at write time, but the error message from a schema violation is less helpful than a Pydantic validation error. Use `Literal["low", "normal", "high", "critical"]`. | Correctness |

---

## What Looks Good

- **`filesystem.py` `file_edit` uniqueness check** — Requiring `old_text` to appear exactly once before replacing prevents accidental multi-site edits. Clean safety guard.
- **`confirmations.py`** — The module-level design is pluggable and correctly handles both async and sync `request_input` implementations, normalising the response to a typed `ConfirmationResponse`.
- **`tools/agents/audit.py` progress reporting** — `report_step` calls at each phase (validate → audit → summarise → persist → review) give clients an accurate progress stream.
- **`work/tasks.py` RRF search** — Hybrid vector + FTS with `rrf_fuse` for task search is a good recall strategy.
- **FastMCP `Depends(db_get_connection)` injection** — Used consistently; keeps tool functions testable via DI without direct import of the global connection.
- **`namespace:filesystem` lazy activation** — The tools are hidden by default. This is a meaningful mitigation for the path traversal risk, limiting exposure to sessions that explicitly activate the namespace.

---

## Verdict

**Request Changes** — The unrestricted filesystem access is the single most impactful open issue across the entire codebase. All other items are improvements.
