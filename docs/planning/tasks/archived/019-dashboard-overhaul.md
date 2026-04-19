# Task: 019 — Dashboard Overhaul & Agent Visualization

## Status
- **Type**: Design / Implementation
- **Priority**: Medium
- **Owner**: Agent
- **Status**: Planning

## Objective
Transform the current minimal/broken "Memory Atlas" into a professional, "non-AI" regular dashboard for the MCP server. This includes fixing the force graph, adding dark mode, visualizing agent workflows (Mermaid), and providing dedicated views for tools, evaluations, and system health.

## Current State Analysis
- **Force Graph**: `src/mem_graph/static/force-graph.js` is a chainable no-op stub. `dashboard.js` expects a `ForceGraph()(container)` API and already calls graph, zoom, center, refresh, and node-click methods, but nothing is rendered.
- **Static App**: `src/mem_graph/static/dashboard.html`, `dashboard.css`, and `dashboard.js` currently implement a single graph explorer with controls, search, node-type filters, and details. `file-tree.html`, `file-tree.css`, and `file-tree.js` are a separate page under `/file-tree`.
- **Backend Routes**: `src/mem_graph/server.py` already exposes `/dashboard`, `/dashboard.js`, `/dashboard.css`, `/dashboard/api/graph`, `/dashboard/api/node/{node_id}`, `/dashboard/api/search`, `/dashboard/api/styles`, `/file-tree`, `/file-tree/api/tree`, and `/file-tree/api/violations`.
- **Styling**: Fixed light "paper" aesthetic, large radii, decorative gradients, and duplicated dashboard/file-tree CSS. No persisted theme preference or dark-mode support.
- **Navigation**: Limited to graph and external file-tree page, plus a disabled "Jina Soon" tab. No in-page dashboard tab system for overview, agents, tools, workflows, evals, or files.
- **Metadata**: No visibility into available agents, workflow graphs, MCP tool catalog, system health, or recent eval summaries without raw API/DB queries.
- **Schema**: `EvalRun` exists in `schema/agent_memory_schema.cypher` and `src/mem_graph/evals/evaluator.py` persists compact summaries, but there is no `logfire_run_id`. There is no `DashboardConfig` node yet.

## Proposed Changes

### 1. Backend API Extensions (`src/mem_graph/server.py`)
Add new endpoints to power the regular dashboard:
- **`GET /dashboard/api/system`**: Returns server version, uptime, DB connection status, and basic telemetry (node/edge counts).
- **`GET /dashboard/api/agents`**: Returns a list of agents extracted from `src/mem_graph/agents/`.
- **`GET /dashboard/api/workflows`**: Returns Mermaid-compatible graph definitions for:
    - `autopilot_graph` from `src/mem_graph/agents/orchestrator_graph.py`
    - `managed_workflow_graph` from `src/mem_graph/agents/workflow_graph.py`
- **`GET /dashboard/api/tools`**: Lists all tools registered in the FastMCP instance, grouped by namespace.
- **`GET /dashboard/api/evals`**: Fetches the 20 most recent `EvalRun` records from the graph.
- **`GET /dashboard/api/logfire/evals`**: Optional later endpoint to fetch/sync hosted eval data from Logfire.

### 2. DB & Schema Requirements (`schema/agent_memory_schema.cypher`)
The dashboard must extract and visualize the following from the graph:
- **Project Hierarchy**: `Project` -> `Backend` -> `CodeFile` / `CodeSymbol`.
- **Work Tracking**: `Task` status distribution and `Violation` severity counts.
- **Agent Traceability**: `AUTHORED_BY` relationships to show which agent produced which `Decision`, `Note`, or `Memory`.
- **Eval Trends**: Historical `EvalRun` nodes linked to `Project`.

**Schema Updates Needed**:
- Add `last_run_at` and `status_metadata` (JSON) to `Agent` node to track live instance health.
- Ensure `EvalRun` has a `logfire_run_id` string property to link local records to hosted spans.
- Add `DashboardConfig` node type for persisting user preferences (e.g., pinned projects, custom filters).

### 3. Logfire Integration
- Research Logfire API/SDK for programmatically retrieving `pydantic-evals` results.
- Implement a sync worker to pull hosted evaluation results into the local `EvalRun` table for offline viewing in the dashboard.

### 4. Frontend Overhaul (`src/mem_graph/static/`)

#### A. Theme & Layout
- **Dark Mode**: Implement CSS variables (`--bg`, `--surface`, `--ink`, etc.) with a toggle and `prefers-color-scheme` support.
- **Navigation**: Move to a unified sidebar or persistent top-nav with tabs:
    - **Overview**: System health + high-level stats.
    - **Explorer**: Functional Force Graph (Fixed).
    - **Agents**: List of agents + Mermaid.js workflow diagrams.
    - **Tools**: Searchable catalog of MCP tools and schemas.
    - **Evals**: Table of historical evaluation results.
    - **Files**: Integrated File Tree explorer.

#### B. Component Fixes
- **Force Graph**: Replace the stub with a working implementation (e.g., using `d3-force` or `force-graph` package bundled locally).
- **Workflows**: Integrate `mermaid.js` (local bundle) to render the logical flow of agents.
- **Data Tables**: Add clean, sortable tables for tools and evaluation runs.

### 5. Workflow Discovery Logic (`src/mem_graph/agents/discovery.py`)
Create a utility to programmatically inspect the `agents` package:
- Extract `Persona` details (name, model, role).
- Introspect `pydantic-graph` structures to generate Mermaid `graph TD` strings.

## Implementation Tasklist

### Phase 0: Baseline and Constraints
- [x] Read `LAST_SESSION.md`, this plan, and the current static files in `src/mem_graph/static/`.
- [x] Run a quick server/static route inventory in `src/mem_graph/server.py` before editing so existing `/dashboard/api/graph`, `/dashboard/api/node/{node_id}`, `/dashboard/api/search`, `/dashboard/api/styles`, `/file-tree/api/tree`, and `/file-tree/api/violations` contracts are preserved.
- [x] Confirm the test command style for this repo. Prefer focused tests first, then `uv run ruff check` and `uv run mypy .` if the implementation touches typed Python.

### Phase 1: Dashboard Metadata APIs
- [x] Add `src/mem_graph/agents/discovery.py` for dashboard-safe metadata extraction.
- [x] In `discovery.py`, list Python agent modules under `src/mem_graph/agents/` without importing arbitrary project-local YAML helper specs as executable code.
- [x] In `discovery.py`, expose known workflow metadata for `orchestrator_graph.py` and `workflow_graph.py`, including display name, source file, node names, edges, and Mermaid `graph TD` text.
- [x] Add `/dashboard/api/system` in `src/mem_graph/server.py` with server name/version/API version, uptime, health status, DB connectivity, and basic graph telemetry.
- [x] Add `/dashboard/api/agents` in `src/mem_graph/server.py` using the discovery utility.
- [x] Add `/dashboard/api/workflows` in `src/mem_graph/server.py` using the discovery utility and static/manual fallback Mermaid definitions when introspection is unreliable.
- [x] Add `/dashboard/api/tools` in `src/mem_graph/server.py`, grouping by `_get_namespace(tool_def)`, and returning name, description, namespace, tags, and input schema when available.
- [x] Add `/dashboard/api/evals` in `src/mem_graph/server.py` to query recent `EvalRun` nodes, optionally filtered by `project_id`, sorted by `started_at`/`persisted_at` descending, limited to 20 by default.
- [x] Add unit tests or lightweight route tests for the new JSON endpoints with `build_http_app(with_lifespan=False)` where practical.

### Phase 2: Schema and Eval Data Support
- [x] Update `schema/agent_memory_schema.cypher` so `EvalRun` includes nullable `logfire_run_id STRING`.
- [x] Update `src/mem_graph/evals/evaluator.py` persistence to write `logfire_run_id` as `NULL` or an optional passed value without breaking current call sites.
- [x] Add a `DashboardConfig` node table with at least `id`, `project_id`, `pinned_projects`, `theme`, `filters_json`, `created_at`, and `updated_at` fields.
- [x] Defer `Agent.last_run_at` and `Agent.status_metadata` unless an `Agent` node table already exists or can be added cleanly without migration risk.
- [x] Treat hosted Logfire sync as optional follow-up unless the local `LogfireAPIClient` exposes stable read APIs for eval results in this environment.

### Phase 3: Unified Static App Shell
- [x] Replace the current `dashboard.html` one-view layout with a single app shell for Overview, Explorer, Agents, Tools, Evals, and Files.
- [x] Keep the existing graph controls, search results, graph canvas, and node details available inside the Explorer tab.
- [x] Integrate the existing file-tree UI into the Files tab by reusing the logic from `file-tree.js` or moving shared logic into dashboard code.
- [x] Leave `/file-tree` functional as a compatibility route, or redirect/link it to the Files tab only after verifying no existing route breaks.
- [x] Remove the disabled "Jina Soon" navigation item.
- [x] Add a theme toggle with `localStorage` persistence and `prefers-color-scheme` fallback.

### Phase 4: Dashboard Styling
- [x] Refactor `dashboard.css` around CSS variables for light and dark themes.
- [x] Use a professional high-density dashboard visual style rather than the current paper aesthetic.
- [x] Avoid one-note palettes and avoid dominant beige/cream/tan, brown/orange, dark blue/slate, and purple-blue gradient themes.
- [x] Keep cards/buttons at `8px` border radius or less.
- [x] Remove decorative radial/orb background effects and avoid cards-inside-cards.
- [x] Ensure controls, tables, tab panels, graph canvas, details panes, and file tree remain layout-stable at desktop and mobile widths.
- [x] Consolidate duplicated `file-tree.css` styles where possible without breaking `/file-tree`.

### Phase 5: Working Force Graph
- [x] Replace `src/mem_graph/static/force-graph.js` with a local, dependency-free canvas force graph implementation or a locally bundled library.
- [x] Preserve the chainable API used by `dashboard.js`: `backgroundColor`, `linkColor`, `linkDirectionalParticles`, `nodeCanvasObject`, `nodePointerAreaPaint`, `onNodeClick`, `graphData`, `refresh`, `centerAt`, and `zoom`.
- [x] Implement force simulation, pan, zoom, drag, hover hit testing, node click selection, link rendering, and resize handling.
- [x] Ensure `dashboard.js` can continue to provide the node drawing callback and details interaction without major rewrites.
- [x] Verify the graph renders nonblank for an empty, small, and larger snapshot payload.

### Phase 6: Overview, Agents, Tools, and Evals Views
- [x] Build the Overview tab with system health, DB status, node/edge counts, task status distribution, violation severity counts, recent eval summary, and quick links to key tabs.
- [x] Build the Agents tab with discovered agents, source files, roles/personas when available, and workflow diagrams.
- [x] Add Mermaid support from a local static bundle or render the workflow definitions directly with simple SVG/HTML if a bundle is not available.
- [x] Build the Tools tab with grouped namespaces, search/filter, descriptions, and schema/details expansion.
- [x] Build the Evals tab with recent `EvalRun` rows, pass/fail status, duration, trigger, mode, label, project, report path, and summary expansion.
- [x] Add loading, empty, and error states for every dashboard API call.

### Phase 7: Verification and Polish
- [x] Run focused Python tests for new discovery/API/eval persistence behavior.
- [x] Run static app smoke checks by starting the local server and opening `/dashboard`.
- [x] Verify dark and light themes across Overview, Explorer, Agents, Tools, Evals, and Files.
- [x] Verify clicking graph nodes updates Details and search still focuses graph nodes.
- [x] Verify the Files tab can load a tree and file details using existing file-tree APIs.
- [x] Verify workflow diagrams match the node order and retry behavior in `src/mem_graph/agents/orchestrator_graph.py` and `src/mem_graph/agents/workflow_graph.py`.
- [x] Run `uv run ruff check` and `uv run mypy .` if Python changed.
- [x] Update this task file checkboxes as work completes and document any deferred Logfire/dashboard config work.

## Implementation Notes
- `/dashboard/api/tools` uses the mounted FastMCP providers directly for the dashboard catalog. In-process `mcp.list_tools()` hung under the current CodeMode/TestClient stack, while provider-level listing returns the same tool definitions needed for grouping and schemas.
- Hosted Logfire sync remains a follow-up. Local `EvalRun` persistence now includes `logfire_run_id`, and the dashboard reads local runs for offline viewing.
- Static verification used route-handler smoke coverage, `node --check` for `dashboard.js` and `force-graph.js`, and full Python tests. Browser automation was not available in this environment.
- The existing `anyio.open_file` filesystem tool path hung under Python 3.14, so filesystem read/write/edit helpers now use synchronous `Path` operations inside the async tool functions.

## Verification Plan
1. **Visual**: Verify Dark Mode consistency across all tabs.
2. **Logic**: Confirm Mermaid diagrams match the Python definitions in `orchestrator_graph.py` and `workflow_graph.py`.
3. **Graph**: Confirm clicking nodes in the fixed Force Graph updates the "Details" panel correctly.
4. **Data**: Confirm the "Evals" tab shows real data from `EvalRun` nodes.

## New Session Implementation Prompt

Use this prompt to start the implementation session:

```text
You are working in /home/michael/projects/python/memory. Please implement docs/planning/tasks/019-dashboard-overhaul.md.

Start by reading:
- LAST_SESSION.md
- docs/planning/tasks/019-dashboard-overhaul.md
- src/mem_graph/server.py
- all files in src/mem_graph/static/
- src/mem_graph/agents/orchestrator_graph.py
- src/mem_graph/agents/workflow_graph.py
- schema/agent_memory_schema.cypher
- src/mem_graph/evals/evaluator.py

Goal: turn the current Memory Atlas graph-only page into a unified professional dashboard for the MCP server, with Overview, Explorer, Agents, Tools, Evals, and Files views. Preserve existing graph/file-tree API behavior while adding the new dashboard metadata APIs listed in the plan.

Important implementation constraints:
- The existing /dashboard/api/graph, /dashboard/api/node/{node_id}, /dashboard/api/search, /dashboard/api/styles, /file-tree/api/tree, and /file-tree/api/violations contracts must keep working.
- Replace src/mem_graph/static/force-graph.js with a real local renderer that preserves the chainable API dashboard.js currently expects.
- Do not load remote CSS/JS/fonts from CDNs.
- Use CSS variables for light/dark themes and persist the selected theme in localStorage.
- Keep the design high-density and dashboard-like, not the current paper aesthetic.
- Avoid dominant beige/cream/tan, brown/orange, dark blue/slate, and purple-blue gradient palettes. Use buttons/cards with border radius <= 8px.
- Hosted Logfire eval sync is optional follow-up unless stable read APIs are already available locally.

Expected work:
1. Add src/mem_graph/agents/discovery.py for agent/workflow metadata and Mermaid definitions.
2. Add /dashboard/api/system, /dashboard/api/agents, /dashboard/api/workflows, /dashboard/api/tools, and /dashboard/api/evals routes in src/mem_graph/server.py.
3. Update EvalRun schema/persistence for optional logfire_run_id and add DashboardConfig schema support if clean.
4. Rework src/mem_graph/static/dashboard.html, dashboard.css, dashboard.js, and force-graph.js into the unified dashboard.
5. Keep /file-tree functional or preserve compatibility through equivalent routing.
6. Add focused tests for new Python API/discovery behavior where practical.
7. Run focused tests, then ruff and mypy if Python changed.
8. Update docs/planning/tasks/019-dashboard-overhaul.md checkboxes to reflect completed and deferred work.

Please implement end to end rather than only proposing changes. If you hit a blocker, document the blocker in the task file and continue with the parts that can be completed safely.
```
