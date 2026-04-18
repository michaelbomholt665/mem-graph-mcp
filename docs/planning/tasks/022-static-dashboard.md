# Task 022: Static Dashboard Refinement - Compact Data-Centric UI

**Status:** Planning  
**Priority:** High  
**Blocked by:** None  
**Blocks:** None

## Problem Statement

The current dashboard design is built for touch screens and takes up excessive space with large metric cards and full-screen layouts. The dashboard should display actual project data (agents, tools, evals) from the filesystem rather than placeholder API responses. Several new pages are needed to explore services, resources, models, and observability data.

### Key Issues

1. **Dashboard (Overview) page**: Metric cards are oversized for desktop viewing; entire page wastes horizontal space
2. **Agents page**: Shows API agents, not the actual agent modules in `src/mem_graph/agents/`; no helper agent organization
3. **Tools page**: Shows API tools, not actual tools from `src/mem_graph/tools/` with folder-based grouping
4. **Evals page**: Shows API eval runs, not actual eval suites from `src/mem_graph/evals/`
5. **Files page**: No dark mode support; file tree takes entire screen; no file details/stats column
6. **Missing pages**: No explorer for Services, Resources, Models, or Observability (prompts/personas/skills)

## Objectives

- **Compact dense layouts** for desktop use (CSS grid compaction, micro typography)
- **Real data from filesystem** (agents, tools, evals, services, resources, models)
- **Proper dark mode** on all pages (especially files page)
- **Two-column file explorer** with code preview and metadata (LOC, function count, comments)
- **New pages** for Services, Resources, and Models (and optional Observability)
- **Helper agent organization** under parent agents on agents page

## Proposed Changes

### 1. Dashboard (Overview) - Compact Layout

**Current issues**: 4-column grid @ `1fr` width, 28px padding, large 26px values, massive spacing

**Changes**:
- Reduce metric card height: `18px padding` → `12px padding`, `26px value font` → `20px font`
- Metric grid: `grid-template-columns: repeat(4, 1fr)` → `repeat(6, 1fr)` (6 cards: Health, DB, Nodes, Edges, Uptime, Tasks)
- Reduce content-grid gap: `14px` → `8px`
- Compact task-row: `10px 0` → `6px 0`, font `12px` → `11px`
- Panel padding: `16px` → `12px`
- Remove agent preview section OR make it a compact 1-row list

**HTML layout**:
- Reduce `.page-content` padding: `28px` → `16px`
- Optional: Combine "Task Status" + "Violations" into single row with left/right split

### 2. Agents Page - Real Data from Filesystem

**Current structure** (`src/mem_graph/agents/`):
```
agents/
├── audit/audit_agent.py
├── builder/agent_builder.py
├── document/{decision,scribe,task,triage}_agent.py
├── fix/fixer_agent.py
├── map/{chat,diagram,map}_agent.py
├── validate/{sentry,validation}_agent.py
├── orchestrator_agent.py      # Top-level helper
├── router_agent.py             # Top-level helper
├── workflow_graph.py           # Helper
└── discovery.py                # Helper
```

**Agent logic**:
- Main agents: `audit`, `builder`, `document`, `fix`, `map`, `validate` (6 agent categories)
- Each category has 1-3 agent implementations (e.g., `document` has `DecisionAgent`, `ScribeAgent`, `TaskAgent`, `TriageAgent`)
- Top-level files (`orchestrator_agent.py`, `router_agent.py`) are helpers, not display agents

**Changes**:
- New endpoint `/dashboard/api/agents-filesystem` that scans `src/mem_graph/agents/` directory
- Returns structure: `{ agents: [ { category: "map", agents: ["ChatAgent", "DiagramAgent", "MapAgent"], description: "...", file_count: 3 }, ... ], helpers: [ "orchestrator_agent", "router_agent", "workflow_graph" ] }`
- Update `agents.js` to fetch filesystem data instead of API data
- Render: Main agent categories in left column (grouped); click to expand shows individual agent files with line counts
- Display helpers as collapsible section at bottom

**New page structure** (agents page):
```
┌─ Topbar (compact) ─────────────────────────────────┐
├─ Main (flex row, height: calc(100vh - 120px)) ─────┤
│  ┌─ Agents Sidebar (240px) ──┐ ┌─ Agent Detail ────┤
│  │ • audit (3 agents)        │ │ • Agent name      │
│  │ • builder (1 agent)       │ │ • File path       │
│  │ • document (4 agents)     │ │ • LOC, imports    │
│  │ • fix (1 agent)           │ │ • Prompt preview  │
│  │ • map (3 agents)          │ │ • Model/provider  │
│  │ • validate (2 agents)     │ │                   │
│  │ [expand] Helpers (7)      │ │ Workflow graph    │
│  └───────────────────────────┘ └───────────────────┤
└──────────────────────────────────────────────────────┘
```

### 3. Tools Page - Real Data from Filesystem

**Current structure** (`src/mem_graph/tools/`):
```
tools/
├── agents/{orchestrator,diagrams,triage,map,audit}.py
├── background/{progress,task_status}.py
├── graph/{graph_queries,resources}.py
├── memory/{memory,conversation,notes}.py
├── integrations/{jina}.py
├── confirmations.py
└── __init__.py (main catalog export)
```

**Changes**:
- New endpoint `/dashboard/api/tools-filesystem` that scans `src/mem_graph/tools/` directory
- Returns: `{ namespaces: [ { namespace: "agents", tools: [...], file_count: 5 }, ... ] }`
- Group by top-level folder (agents, background, graph, memory, integrations, root tools)
- Update `tools.js` to use namespace folder-based coloring

**Display**:
- Namespace filter chips: agents, background, graph, memory, integrations (dark colors)
- Table columns: **Namespace** | **Tool Name** | **Function** | **File** | **LOC**
- Expandable row for source code preview

### 4. Evals Page - Real Data from Filesystem

**Current structure** (`src/mem_graph/evals/`):
```
evals/
├── audit_evals.py
├── document_evals.py
├── fix_evals.py
├── map_evals.py
├── validate_evals.py
├── evaluator.py
├── fixtures.py
├── logfire_client.py
└── scorers.py
```

**Changes**:
- New endpoint `/dashboard/api/evals-filesystem` that scans `src/mem_graph/evals/` directory
- Returns: `{ evals: [ { name: "AuditEvals", file: "audit_evals.py", suites: 3, loc: 142 }, ... ], helpers: ["evaluator", "fixtures", "scorers"] }`
- Update `evals.js` to show filesystem evals (not API eval runs)

**Display** (new design):
- Left column: Eval categories (audit, document, fix, map, validate) with test suite count + file LOC
- Right column: Click to view source code, test suite list, fixtures used
- Helper files at bottom

### 5. Files Page - Dark Mode + Two-Column Layout

**Issues**: 
- No dark mode application
- File tree takes full width
- No file preview or metadata

**Changes**:
- Dark theme CSS: ensure `.tree-root`, `.tree-row` have dark backgrounds
- Layout: change `.files-grid` from `minmax(0, 1fr) 420px` to `280px 1fr` (reversed, sidebar first)
- File tree: max 280px width, no horizontal scroll allowed
- Right column: file details panel
  - Selected file metadata: path, size, LOC, function count, comment ratio
  - Code preview (first 50 lines of syntax-highlighted code, truncated)
  - File type icon + MIME type badge
  - Modification date + file size

**File metadata display** (panel):
```
File: path/to/file.py
─────────────────────
Size: 4.2 KB
Lines: 142
Functions: 5
Classes: 2
Comments: 18 (12.7%)
Docstrings: 3

Code preview (syntax highlighted):
import json
from typing import List
...
```

**CSS dark mode fix**:
- Ensure `.tree-row` has `background: #0d1014` 
- `.tree-row:hover` → `background: #0f1520`
- `.result-button` → dark background + accent hover
- File details panel should inherit `.panel` dark styling

### 6. Services Page (NEW)

**Source**: `src/mem_graph/services/`

**Files**:
- `code_embed_service.py` — Vector embedding for code
- `text_embed_service.py` — Vector embedding for text
- `memory.py` — Graph memory operations
- `search.py` — Semantic search
- `summarizer.py` — Multi-level summarization
- `task_queue.py` — Background task scheduling
- `report_writer.py` — Report generation
- `violation_writer.py` — Violation logging
- `fingerprint.py` — Code fingerprinting
- `jina_common.py` — Jina embedding commons

**Page design**:
- Left column: list of services with file size, LOC, dependencies
- Right column: service details (entry point, public methods, docstring)
- Code preview (first 30 lines)
- Dependency graph (what other services/modules depend on this)

### 7. Resources Page (NEW)

**Source**: `src/mem_graph/resources/`

**Files**:
- `personas.py` — Agent personas (Persona class, big-five traits, role definitions)
- `prompts.py` — Prompt templates  
- `coding_standards.py` — Code style resources + architecture constraints
- `architecture.py` — Architecture guide + design decisions

**Page design**:
- Left column: resource categories (personas, prompts, coding standards, architecture)
- Click to expand:
  - **Personas**: List persona names, traits, base_instructions (extract from code)
  - **Prompts**: List prompt template names + preview
  - **Coding Standards**: List guideline categories
  - **Architecture**: List architecture decisions

**Display format**:
```
Personas (8)
├── PreciseEngineer
├── CreativeExplorer
├── DetailOrientedScribe
└── ...

Prompts (12)
├── audit_system_prompt
├── code_review_prompt
└── ...

Coding Standards (5 categories)
Constraints (8 rules)
```

### 8. Models Page (NEW)

**Source**: `src/mem_graph/models/`

**Files**:
- `audit.py` — Audit findings models
- `code.py` — Code symbol models (Function, Class, Module)
- `conversation.py` — Conversation + memory models
- `evals.py` — Eval result models
- `memory.py` — Memory record models
- `project.py` — Project models
- `task.py` — Task/work models
- `work.py` — Work item models

**Page design**:
- Left column: model categories (code, memory, audit, task, conversation, eval, project, work)
- Right column: model details
  - Class name + docstring
  - Fields: name, type, description, required/optional
  - Example JSON instance

**Display format** (expandable schema):
```
CodeSymbol
├── type: Literal["function", "class", "module"]
├── name: str (required)
├── file_path: str (required)
├── line_start: int (required)
├── line_end: int (required)
├── docstring: str | None
├── decorators: list[str]
├── is_async: bool
└── parameters: list[Parameter]

[Example JSON]
{
  "type": "function",
  "name": "process_file",
  "file_path": "src/mem_graph/services/code_embed_service.py",
  ...
}
```

### 9. Observability Page (OPTIONAL - deferred)

**Source**: `src/mem_graph/observability/`

**Files**:
- `instrumentation.py` — OpenTelemetry instrumentation setup
- `logfire_setup.py` — Logfire integration
- `metrics.py` — Custom metrics definitions
- `otel_setup.py` — OTEL SDK configuration

**Page design** (if implemented):
- Overview metrics: span count, log events, error rate
- Instrumentation checklist (which libraries are instrumented)
- Metrics catalog (custom metrics being tracked)

**Decision**: This page is lower priority; can be deferred to phase 2.

## Implementation Plan

### Phase 1: Backend API Endpoints (New)

1. **`/dashboard/api/agents-filesystem`** — Scan `src/mem_graph/agents/`, return category structure + helpers
2. **`/dashboard/api/tools-filesystem`** — Scan `src/mem_graph/tools/`, return namespace structure
3. **`/dashboard/api/evals-filesystem`** — Scan `src/mem_graph/evals/`, return eval suites + helpers
4. **`/dashboard/api/services`** — Scan `src/mem_graph/services/`, return service metadata (LOC, docstring, dependencies)
5. **`/dashboard/api/resources`** — Parse `src/mem_graph/resources/`, extract personas/prompts/standards/architecture
6. **`/dashboard/api/models`** — Parse `src/mem_graph/models/`, extract model schemas + docstrings
7. **`/dashboard/api/observability`** (optional) — Return instrumentation status, metric list

**Implementation approach**:
- Use `pathlib` + `ast` parsing to extract Python module metadata
- Cache results to avoid repeated filesystem scans
- Return structured JSON with LOC, imports, docstrings, function lists

### Phase 2: Frontend CSS + Layout

1. Update `dashboard.css`:
   - Compact `.metric-grid` (6 columns)
   - Reduce card padding/font sizes
   - Tighten spacing throughout

2. Create/update `files.css`:
   - Dark theme fixes (backgrounds, text colors)
   - Two-column layout (280px + 1fr)

3. Update `evals.css`:
   - Change from two-column run list to single-column suite list

4. Create `services.css`, `resources.css`, `models.css`:
   - Left sidebar (200px) + main content (1fr)
   - Expandable category sections
   - Code block styling

### Phase 3: Frontend JS + Pages

1. Update `dashboard.js` — reduce spacing, no agent preview (or make it compact)

2. Rewrite `agents.js`:
   - Fetch `/dashboard/api/agents-filesystem`
   - Render category list (left) + agent detail (right)
   - Click handler for agent selection
   - Show helpers in collapsible section

3. Update `tools.js`:
   - Fetch `/dashboard/api/tools-filesystem`
   - Render namespace-based table (not just filter chips)
   - Show file path + LOC in table

4. Update `evals.js`:
   - Fetch `/dashboard/api/evals-filesystem`
   - Render eval suite list (not run list)
   - Show fixture dependencies

5. Update `file-tree.js`:
   - Add file details panel rendering
   - Extract LOC, function count, comment ratio
   - Syntax highlighting for code preview

6. Create `services.js`:
   - Fetch `/dashboard/api/services`
   - Left column: service list
   - Right column: service details + code preview

7. Create `resources.js`:
   - Fetch `/dashboard/api/resources`
   - Render persona/prompt/standards/architecture categories
   - Expandable sections

8. Create `models.js`:
   - Fetch `/dashboard/api/models`
   - Render model schema explorer
   - Show example JSON instances

### Phase 4: New HTML Pages

1. `services.html` — Layout + topbar/sidebar, left panel + main content
2. `resources.html` — Same layout, resource categories
3. `models.html` — Same layout, model schemas
4. `observability.html` (optional) — Instrumentation + metrics dashboard

Update sidebar navigation to include new pages.

## Testing Strategy

1. **Filesystem scanning**:
   - Verify agent/tool/eval counts match actual filesystem
   - Check LOC counts against `wc -l`
   - Validate docstring extraction from Python AST

2. **Dark mode**:
   - Visual check on all new pages
   - Ensure text contrast > 4.5:1 (WCAG AA)

3. **Compact layout**:
   - Screenshot comparison: original vs. new dashboard
   - Verify all content fits in 1920x1080 without scroll

4. **New pages**:
   - Verify each page loads without JS errors
   - Check navigation between pages
   - Validate sidebar active state

## Success Criteria

- [ ] Dashboard overview compact: < 2 scrolls on 1440x900
- [ ] Agents page shows real agent modules (audit, builder, document, fix, map, validate) + helpers
- [ ] Tools page shows tools from filesystem folders (agents, background, graph, memory, integrations)
- [ ] Evals page shows actual eval suites (audit_evals, document_evals, etc.)
- [ ] Files page: dark mode works, tree 280px max, file details panel shows metadata + code preview
- [ ] Services, Resources, Models pages functional with real data
- [ ] All pages use consistent dark theme, no light mode leakage
- [ ] All pages responsive to 1440x900 without horizontal scroll

## Related Files

- **Current dashboard API**: `src/mem_graph/app/dashboard_routes.py` (extends existing routes)
- **CSS files**: `src/mem_graph/static/style/{dashboard,evals,file-tree}.css` + new `.css` files
- **HTML pages**: `src/mem_graph/static/{dashboard,agents,tools,evals,file-tree}.html` + new `.html` files
- **JS modules**: `src/mem_graph/static/js/{dashboard,agents,tools,evals,file-tree}.js` + new `.js` files
- **Design reference**: `docs/planning/design/dashboard/*.html` (prototypes)

## Notes

- Helper agents (orchestrator_agent, router_agent) should be grouped visually but not promoted as primary agents
- Services page can use architecture.py's architecture decisions as reference context
- Resources page can extract Persona instances using Python's `getmembers()` introspection
- Models page benefits from type hints; can use `typing.get_type_hints()` for schema extraction
- Consider async filesystem scanning for large codebases; use caching to avoid repeated I/O
