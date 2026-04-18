# Phase 5a Dashboard Tasklist

## Goal

Create a lightweight dashboard that lets users inspect the knowledge graph visually, search nodes, and follow relationships without introducing a heavyweight frontend stack.

Prerequisite: See `docs/planning/tasks/007-fastmcp-task.md` — FastMCP readiness is not required to build the dashboard, but complete 007 before wiring FastMCP-specific integrations.

## Dependencies

- Depends on graph data being queryable from the current Ladybug/Kuzu layer.
- Should stay compatible with the future Jina and file-explorer views planned after this phase.
- Use the structure described in `docs/planning/design/009-phase5a-dashboard.md` and `docs/planning/design/FILE_STRUCTURE.md`.

## Work Envelope

- Planned new files: 8
- Planned file edits: 3-4
- Shape: new-file biased, single task
- Why this size works: the UI and graph API fit comfortably inside one task without breaking the 15 new-file limit

## Planned Files

New files:
- `src/mem_graph/tools/graph/__init__.py`
- `src/mem_graph/tools/graph/graph_queries.py`
- `src/mem_graph/tools/graph/resources.py`
- `src/mem_graph/static/dashboard.html`
- `src/mem_graph/static/dashboard.js`
- `src/mem_graph/static/dashboard.css`
- `src/mem_graph/resources/node_styles.json`
- `tests/test_graph.py`

Existing files to edit:
- `src/mem_graph/server.py`
- `src/mem_graph/tools/__init__.py`
- `docs/documentation/architecture.md`
- `docs/documentation/server.md`

## Tasklist

- [x] Add graph-query tool models for node snapshots, edge snapshots, and node-detail payloads.
- [x] Implement `get_graph_snapshot`, `get_node_details`, and `search_graph` against the existing graph client with bounded depth and filtering.
- [x] Define stable resource and route names so the dashboard can fetch graph data without coupling to internal tool names.
- [x] Build a static dashboard shell with a canvas, filter controls, search input, and a details panel.
- [x] Implement dashboard JavaScript for initial load, periodic refresh, node selection, search focus, and type filtering.
- [x] Add CSS that keeps the dashboard readable on laptop screens without assuming a full design-system rewrite.
- [x] Add node-style metadata so graph types are colored and sized consistently across refreshes.
- [x] Mount dashboard routes and static assets in the server without breaking existing MCP endpoints.
- [x] Add tests for graph snapshot shaping, query filtering, and route responses.
- [x] Document how to launch the dashboard, what node types are visible, and what is intentionally deferred.

## Out Of Scope

- WebSocket live updates
- Multi-user sessions
- Complex custom node rendering beyond color, size, and labels

## Done When

- [x] A browser route renders the dashboard and loads graph data from server APIs.
- [x] Search, node selection, and type filters work on real graph data.
- [x] The dashboard remains responsive on moderately sized graphs.
- [x] The implementation leaves room for Jina and file-explorer tabs instead of boxing them out.

## References

- `docs/planning/design/009-phase5a-dashboard.md`
- `docs/planning/design/005-hindsight.md`
- `docs/planning/design/FILE_STRUCTURE.md`
- `docs/planning/design/links.md`
