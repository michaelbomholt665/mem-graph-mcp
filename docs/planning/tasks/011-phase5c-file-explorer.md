# Phase 5c File Explorer Tasklist

## Goal

Add a file-tree view that complements the graph dashboard by showing project hierarchy, violation counts, and last-audited metadata for each file.

Prerequisite: See `docs/planning/tasks/007-fastmcp-task.md` — file-explorer UI can be built independently; ensure 007 is done before connecting FastMCP-driven audit updates.

## Dependencies

- Should reuse the static asset and route patterns established by the dashboard task.
- Depends on violation data already existing in the graph and filesystem tools remaining the source of truth for file-path semantics.
- Follow `docs/planning/design/011-phase5c-files.md` and the target layout in `docs/planning/design/FILE_STRUCTURE.md`.

## Work Envelope

- Planned new files: 6
- Planned file edits: 4-5
- Shape: balanced, single task
- Why this size works: tree API, static UI, and validation tests stay well within the per-task file cap

## Planned Files

New files:
- `src/mem_graph/tools/filesystem/tree.py`
- `src/mem_graph/tools/filesystem/status.py`
- `src/mem_graph/static/file-tree.html`
- `src/mem_graph/static/file-tree.js`
- `src/mem_graph/static/file-tree.css`
- `tests/test_filesystem_tree.py`

Existing files to edit:
- `src/mem_graph/server.py`
- `src/mem_graph/tools/__init__.py`
- `src/mem_graph/tools/filesystem/__init__.py`
- `docs/documentation/tools.md`
- `docs/documentation/architecture.md`

## Tasklist

- [ ] Add filesystem tree models that can represent directories, files, violation counts, violation types, and last-audited timestamps.
- [ ] Implement `get_file_tree` with hidden-file filtering, stable sort order, and optional graph-enriched metadata.
- [ ] Implement `get_file_violations` so the explorer can show file-level details without duplicating audit logic in the UI.
- [ ] Add a static file-explorer page with hierarchical navigation and a details pane for violations.
- [ ] Implement explorer JavaScript for expand/collapse, selection state, and loading file-specific violation details.
- [ ] Add styling that keeps large trees usable and makes violation badges visually obvious.
- [ ] Mount the file-explorer routes in the server and keep them aligned with the dashboard route conventions.
- [ ] Add tests for tree building, ordering, hidden-file exclusion, and violation aggregation.
- [ ] Document the intended relationship between the file explorer and the graph dashboard.

## Out Of Scope

- Editing files from this UI
- Per-language icons or syntax highlighting in the explorer
- Advanced virtualization for extremely large monorepos

## Done When

- [ ] The explorer renders a hierarchical tree with directories first and files second.
- [ ] Violation badges and last-audited metadata are visible when present.
- [ ] Selecting a file shows detailed violation information.
- [ ] The implementation can coexist with the dashboard without route or asset conflicts.

## References

- `docs/planning/design/011-phase5c-files.md`
- `docs/planning/design/009-phase5a-dashboard.md`
- `docs/planning/design/FILE_STRUCTURE.md`
- `docs/planning/design/links.md`