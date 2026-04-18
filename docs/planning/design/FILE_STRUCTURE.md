# Complete File Structure: Post-Implementation

**Status:** Proposed  
**Date:** 2026-04-13  
**Scope:** All 15 design features integrated

This document shows the complete file tree after implementing all design features. **Edited files** are marked with `[EDIT]`. **New files** are unmarked. Existing unchanged files are listed for reference.

---

## Root Directory

```
/home/michael/projects/python/memory/
├── pyproject.toml                           [EDIT] - Update deps (pydantic-ai-slim, no changes otherwise)
├── README.md
├── .env.example
├── .gitignore
├── LICENSE
│
├── docs/
│   ├── planning/
│   │   ├── tasks/
│   │   │   ├── 006-agents-refactor-complete.md
│   │   │   ├── 007-fastmcp-task.md
│   │   │   └── archived/
│   │   │
│   │   └── design/
│   │       ├── INDEX.md                    [DESIGN INDEX - Master reference]
│   │       ├── proposals/
│   │       │   └── pydantic-upgrade.md
│   │       ├── 001-pydantic-ai-slim.md
│   │       ├── 002-pydantic-graph.md
│   │       ├── 003-pydantic-deep.md
│   │       ├── 004-pydantic-ai-skills.md
│   │       ├── 005-hindsight.md
│   │       ├── 006-phase3-interactivity.md
│   │       ├── 007-phase4a-icons.md
│   │       ├── 008-phase4b-tasks.md
│   │       ├── 009-phase5a-dashboard.md
│   │       ├── 010-phase5b-jina.md
│   │       ├── 011-phase5c-files.md
│   │       ├── 012-otel.md
│   │       ├── 013-versioning.md
│   │       ├── 014-evals.md
│   │       └── 015-logfire.md
│   │
│   └── other docs...
│
├── src/mem_graph/
│   ├── __init__.py                         [EDIT] - Add __version__
│   ├── main.py
│   ├── config.py                           [EDIT] - Add model tier constants
│   ├── auth.py
│   ├── db.py                               [EDIT] - Add LogfireGraphClient wrapper
│   ├── logging.py                          [EDIT] - Add TraceContextFilter
│   ├── ids.py
│   ├── embeddings.py
│   │
│   ├── observability/                      [NEW FOLDER]
│   │   ├── __init__.py
│   │   ├── logfire_setup.py               [NEW] - Logfire initialization
│   │   ├── otel_setup.py                  [NEW] - OpenTelemetry setup
│   │   ├── instrumentation.py             [NEW] - Decorators (@traced_tool, @logfire_tool)
│   │   └── metrics.py                     [NEW] - Meter definitions
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── audit.py
│   │   ├── conversation.py
│   │   ├── plan.py                        [NEW] - PlanStatus, PlanStep, Plan models
│   │   ├── task.py                        [NEW] - TaskStatus, Task, TaskProgress models
│   │   ├── evals.py                       [NEW] - EvalTestCase, EvalSuite, EvalResult, EvalReport
│   │   └── confirmation.py                [NEW] - ConfirmationRequest, ConfirmationResponse
│   │
│   ├── providers/
│   │   └── openapi.py
│   │
│   ├── resources/
│   │   ├── personas.py
│   │   ├── prompts.py
│   │   ├── icons.py                       [NEW] - IconRegistry, TOOL_ICONS
│   │   └── node_styles.json               [NEW] - Style config for dashboard nodes
│   │
│   ├── agents/
│   │   ├── __init__.py                    [EDIT] - AgentFactory with wrapping (Planning, Hindsight)
│   │   ├── router_agent.py                [EDIT] - Use factory with tier selection
│   │   ├── orchestrator_agent.py          [EDIT] - Use factory, tier-based model
│   │   ├── orchestrator_graph.py          [EDIT] - Use Pydantic-Graph BaseNode classes
│   │   │
│   │   ├── planning_agent.py              [NEW] - PlanningAgent wrapper class
│   │   │
│   │   ├── audit/
│   │   │   ├── __init__.py
│   │   │   ├── audit_agent.py             [EDIT] - Model selection per tier (openai:, google:)
│   │   │   └── rule_injector_agent.py
│   │   │
│   │   ├── map/
│   │   │   ├── __init__.py
│   │   │   ├── map_agent.py               [EDIT] - Model selection per tier
│   │   │   ├── chat_agent.py              [EDIT] - Model selection per tier
│   │   │   └── diagram_agent.py           [EDIT] - Model selection per tier
│   │   │
│   │   ├── fix/
│   │   │   ├── __init__.py
│   │   │   └── fixer_agent.py             [EDIT] - Model selection per tier
│   │   │
│   │   ├── validate/
│   │   │   ├── __init__.py
│   │   │   ├── sentry_agent.py            [EDIT] - Model selection per tier
│   │   │   └── validation_agent.py        [EDIT] - Model selection per tier
│   │   │
│   │   └── document/
│   │       ├── __init__.py
│   │       ├── task_agent.py              [EDIT] - Model selection per tier
│   │       ├── decision_agent.py          [EDIT] - Model selection per tier
│   │       ├── triage_agent.py            [EDIT] - Model selection per tier
│   │       └── scribe_agent.py            [EDIT] - Model selection per tier
│   │
│   ├── skills/                            [NEW FOLDER]
│   │   ├── __init__.py                    [NEW] - SkillRegistry with skill toolsets
│   │   ├── memory.py                      [NEW] - MemorySkill with scripts
│   │   ├── work.py                        [NEW] - WorkSkill (tasks, decisions, projects)
│   │   ├── agents.py                      [NEW] - AgentSkill (calls agents as skills)
│   │   └── filesystem.py                  [NEW] - FilesystemSkill
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── summarizer.py
│   │   ├── report_writer.py
│   │   ├── violation_writer.py
│   │   ├── task_queue.py                  [NEW] - TaskQueue for background tasks
│   │   ├── diagrams.py                    [NEW] - Mermaid/chart rendering
│   │   ├── jina_embedder.py               [NEW] - JinaCodeEmbedder with semantic linking
│   │   └── memory.py                      [NEW] - LogfireMemory with instrumentation
│   │
│   ├── evals/                             [NEW FOLDER]
│   │   ├── __init__.py
│   │   ├── audit_evals.py                 [NEW] - AUDIT_EVALS test suite
│   │   ├── fix_evals.py                   [NEW] - FIX_EVALS test suite
│   │   ├── validate_evals.py              [NEW] - VALIDATE_EVALS test suite
│   │   ├── map_evals.py                   [NEW] - MAP_EVALS test suite
│   │   ├── document_evals.py              [NEW] - DOCUMENT_EVALS test suite
│   │   ├── scorers.py                     [NEW] - semantic_similarity_scorer, exact_match_scorer, etc.
│   │   └── evaluator.py                   [NEW] - Evaluator runner class
│   │
│   ├── tools/
│   │   ├── __init__.py                    [EDIT] - Import all tools/agent tools
│   │   │
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py
│   │   │   ├── audit.py                   [EDIT] - Add @audit_package (task=True), logfire instrumentation
│   │   │   ├── diagrams.py
│   │   │   ├── map.py                     [EDIT] - Add @map_codebase (task=True)
│   │   │   └── triage.py                  [EDIT] - Add @triage_violations (task=True)
│   │   │
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   ├── memory.py                  [EDIT] - Add confirmation on delete, @traced_tool, @logfire_tool
│   │   │   ├── conversation.py
│   │   │   └── notes.py
│   │   │
│   │   ├── work/
│   │   │   ├── __init__.py
│   │   │   ├── tasks.py
│   │   │   ├── decisions.py
│   │   │   ├── projects.py
│   │   │   └── violations.py              [EDIT] - Add @traced_tool
│   │   │
│   │   ├── filesystem/
│   │   │   ├── __init__.py
│   │   │   ├── filesystem.py              [EDIT] - Add file read/write instrumentation
│   │   │   ├── tree.py                    [NEW] - get_file_tree, get_file_violations
│   │   │   └── status.py                  [NEW] - File status tracking
│   │   │
│   │   ├── integrations/                  [NEW FOLDER]
│   │   │   ├── __init__.py
│   │   │   ├── jina.py                    [NEW] - fetch_jina_issues, find_code_for_ticket, etc.
│   │   │   └── github.py                  [NEW OPTIONAL - future]
│   │   │
│   │   ├── graph/                         [NEW FOLDER]
│   │   │   ├── __init__.py
│   │   │   ├── graph_queries.py           [NEW] - get_graph_snapshot, get_node_details, search_graph
│   │   │   └── resources.py               [NEW] - Resource URI templates
│   │   │
│   │   ├── background/                    [NEW FOLDER]
│   │   │   ├── __init__.py
│   │   │   ├── task_status.py             [NEW] - get_task_status, cancel_task
│   │   │   └── progress.py                [NEW] - ctx.report_progress wrappers
│   │   │
│   │   └── confirmations/                 [NEW FOLDER]
│   │       ├── __init__.py
│   │       └── handlers.py                [NEW] - require_confirmation, ConfirmationMiddleware
│   │
│   ├── server.py                          [EDIT] - Mount tools, enable CodeMode, setup OTel/Logfire, version
│   │
│   └── static/                            [NEW FOLDER - Frontend assets]
│       ├── dashboard.html                 [NEW] - 3D ForceGraph visualization
│       ├── dashboard.js                   [NEW] - Graph interaction logic
│       ├── dashboard.css                  [NEW] - Graph styling
│       ├── file-tree.html                 [NEW] - File explorer with violations
│       ├── file-tree.js                   [NEW] - Tree interaction
│       ├── file-tree.css                  [NEW] - Tree styling
│       ├── lib/
│       │   ├── d3.v7.min.js               [CDN link in HTML]
│       │   ├── three.min.js               [CDN link in HTML]
│       │   └── 3d-force-graph.min.js      [CDN link in HTML]
│       └── assets/
│           ├── icons/
│           │   ├── brain.svg              [NEW OPTIONAL]
│           │   ├── code.svg               [NEW OPTIONAL]
│           │   └── graph.svg              [NEW OPTIONAL]
│           └── graphs/
│               └── sample.json            [NEW - Sample graph data for testing]
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_evals.py                      [NEW] - Eval suite tests
│   ├── test_agents/
│   │   ├── test_audit_agent.py
│   │   ├── test_fix_agent.py
│   │   ├── test_validate_agent.py
│   │   ├── test_map_agent.py
│   │   └── test_planning_agent.py         [NEW] - Test planning wrapper
│   ├── test_models/
│   │   ├── test_plans.py                  [NEW]
│   │   └── test_tasks.py                  [NEW]
│   ├── test_services/
│   │   ├── test_jina_embedder.py          [NEW]
│   │   ├── test_task_queue.py             [NEW]
│   │   └── test_diagrams.py               [NEW]
│   ├── test_tools/
│   │   ├── test_memory.py                 [EDIT] - Test confirmations
│   │   ├── test_graph.py                  [NEW]
│   │   ├── test_filesystem_tree.py        [NEW]
│   │   └── test_integrations/
│   │       └── test_jina.py               [NEW]
│   ├── test_evals/
│   │   ├── test_audit_evals.py            [NEW]
│   │   ├── test_fix_evals.py              [NEW]
│   │   └── test_scorers.py                [NEW]
│   └── fixtures/
│       ├── sample_code.py                 [NEW - For evals/tests]
│       ├── sample_violations.json         [NEW]
│       └── sample_graph_data.json         [NEW]
│
├── scripts/                               [NEW FOLDER]
│   ├── run_evals.py                       [NEW] - CLI to run all evals
│   ├── setup_dashboards.py                [NEW] - Setup Grafana/Logfire dashboards
│   ├── migrate_agents_to_slim.py          [NEW] - Helper script for model migration
│   └── load_jina_sample_data.py           [NEW] - Test data loader
│
└── .vscode/settings.json                  [OPTIONAL EDIT]
```

---

## Summary of Changes by Category

### **New Folders (8)**
- `observability/` - Logfire + OTel setup
- `skills/` - Pydantic-AI-Skills wrappers
- `evals/` - Stochastic testing framework
- `tools/integrations/` - Jina, GitHub APIs
- `tools/graph/` - Graph query APIs
- `tools/background/` - Task queue management
- `tools/confirmations/` - User elicitation
- `static/` - Frontend assets (dashboard, file tree)

### **New Files (50+)**
**Models:** `plan.py`, `task.py`, `evals.py`, `confirmation.py`
**Services:** `task_queue.py`, `diagrams.py`, `jina_embedder.py`, `memory.py`
**Agents:** `planning_agent.py`
**Skills:** `memory.py`, `work.py`, `agents.py`, `filesystem.py` + `__init__.py`
**Tools:** `tree.py`, `status.py`, `graph_queries.py`, `resources.py`, `task_status.py`, `progress.py`, `handlers.py` + jina.py
**Evals:** `audit_evals.py`, `fix_evals.py`, `validate_evals.py`, `map_evals.py`, `document_evals.py`, `scorers.py`, `evaluator.py`
**Observability:** `logfire_setup.py`, `otel_setup.py`, `instrumentation.py`, `metrics.py`
**Frontend:** `dashboard.html`, `dashboard.js`, `dashboard.css`, `file-tree.html`, `file-tree.js`, `file-tree.css`
**Tests:** `test_evals.py`, `test_planning_agent.py`, `test_plans.py`, `test_tasks.py`, `test_jina_embedder.py`, `test_task_queue.py`, `test_diagrams.py`, `test_graph.py`, `test_filesystem_tree.py`, `test_jina.py`, `test_audit_evals.py`, `test_fix_evals.py`, `test_scorers.py` + fixtures
**Scripts:** `run_evals.py`, `setup_dashboards.py`, `migrate_agents_to_slim.py`, `load_jina_sample_data.py`
**Resources:** `icons.py`, `node_styles.json`

### **Edited Files (30+)**
**Core:** `__init__.py`, `config.py`, `db.py`, `logging.py`, `server.py`
**Agent Factory:** `agents/__init__.py`, `router_agent.py`, `orchestrator_agent.py`, `orchestrator_graph.py`
**All Agent Files:** `audit/audit_agent.py`, `fix/fixer_agent.py`, `validate/sentry_agent.py/validation_agent.py`, `map/map_agent.py/chat_agent.py/diagram_agent.py`, `document/task_agent.py/decision_agent.py/triage_agent.py/scribe_agent.py`
**Tools:** `agents/audit.py`, `agents/map.py`, `agents/triage.py`, `memory/memory.py`, `work/violations.py`, `filesystem/filesystem.py`
**Tests:** `test_tools/test_memory.py`

---

## Key Integration Points

### **Agent Factory** (`agents/__init__.py` [EDIT])
Central point where all agent wrapping happens:
```python
class AgentFactory:
    - create_audit_agent()  # Wraps with Hindsight + Planning(EXPERT)
    - create_fix_agent()    # Wraps with Hindsight + Planning(EXPERT)
    - create_validate_agent()  # Wraps with Hindsight + Planning(always)
    - create_map_agent()    # Wraps with Hindsight + Planning(EXPERT)
    - create_task_agent()   # Wraps with Hindsight + Planning(EXPERT)
```

### **Server** (`server.py` [EDIT])
Mounts all components:
- Tools (memory, work, agents, filesystem, graph, integrations, background, confirmations)
- Skills (SkillRegistry)
- OTel + Logfire setup
- CodeMode transform
- StaticTokenVerifier auth
- Routes for dashboard + file-tree

### **Tools** (`tools/**/*.py` [EDIT])
- Heavy tools marked `task=True` (audit, map, triage)
- Confirmations on destructive ops (memory delete)
- Instrumented with @traced_tool + @logfire_tool

### **Frontend** (`static/` [NEW])
- `dashboard.html/js/css` - ForceGraph + node details
- `file-tree.html/js/css` - File explorer + violations

---

This structure ensures:
✅ No existing code is deleted (only edited)  
✅ All 15 features have their files/locations specified  
✅ Wrapper pattern keeps agent code in place  
✅ Skills wrap existing tools (no duplication)  
✅ Frontend assets are isolated in `/static/`  
✅ Tests mirror implementation structure
