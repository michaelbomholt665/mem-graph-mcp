# Last Session Summary

**Date:** 2026-04-19
**Task:** 025 — Improve Tool / Agent / Prompt / Skill Visibility

## What was implemented

### Discovery model overhaul

- Reworked server discovery in `src/mem_graph/server.py` to use FastMCP native transforms:
  - `ResourcesAsTools(mcp)`
  - `PromptsAsTools(mcp)`
  - `BM25SearchTransform(max_results=8, always_visible=["system_inspect", "list_agents", "list_task_types"])`
- Removed the conflicting `CodeMode()` transform so the runtime now exposes the intended pinned discovery surface:
  - `list_agents`
  - `list_task_types`
  - `system_inspect`
  - `search_tools`
  - `call_tool`
- Updated the server instructions to orient new clients toward `system_inspect`, `search_tools`, prompt/resource browsing, and lazy namespace activation.

### New registries

- Added `src/mem_graph/app/registry.py`
  - `AgentEntry`
  - `register_agent()`
  - `all_agents()`
- Added `src/mem_graph/providers/skills/registry.py`
  - `SkillEntry`
  - `register_skill()`
  - `all_skills()`
  - `resolve_skill()`
  - `task_type_map()`
- Added `src/mem_graph/providers/skills/__init__.py` exports.

### Registry-driven discovery tools

- Refactored `src/mem_graph/app/tools.py`:
  - `list_agents()` now reads from the public agent registry instead of a hardcoded list.
  - `list_task_types()` now exposes the public category → task-type map from the skill registry.
  - `system_inspect()` now returns a one-call orientation snapshot with counts/examples for tools, prompts, resources, agents, skills, and task types.
  - `tools_activate()` kept lazy namespace activation but refreshed its parameter description.
  - Added `catalog_tools()` to inspect the full raw tool catalog across mounted providers.
- Updated:
  - `src/mem_graph/app/web.py` to reuse `catalog_tools()` for dashboard tool inventory.
  - `src/mem_graph/app/lifespan.py` to show raw tool counts and the new BM25 discovery mode in the startup banner.

### Agent self-registration

- Public agent metadata is now registered at import time from the tool modules themselves:
  - `src/mem_graph/tools/agents/audit.py`
  - `src/mem_graph/tools/agents/map.py`
  - `src/mem_graph/tools/agents/triage.py`
  - `src/mem_graph/tools/agents/diagrams.py`
  - `src/mem_graph/tools/agents/orchestrator.py`
  - `src/mem_graph/tools/work/decisions.py`
  - `src/mem_graph/tools/work/tasks.py`
- Registered public agents:
  - Audit Agent
  - Map Agent
  - Triage Agent
  - Diagram Agent
  - Autopilot Remediation
  - Codebase Orchestrator
  - Sub-agent Workflow
  - Decision Agent
  - Task Decomposer

### Tool description audit

- Rewrote MCP tool docstrings across `src/mem_graph/tools/` to one tight sentence each.
- Files updated:
  - `src/mem_graph/tools/agents/audit.py`
  - `src/mem_graph/tools/agents/map.py`
  - `src/mem_graph/tools/agents/triage.py`
  - `src/mem_graph/tools/agents/diagrams.py`
  - `src/mem_graph/tools/agents/orchestrator.py`
  - `src/mem_graph/tools/code/parser.py`
  - `src/mem_graph/tools/filesystem/filesystem.py`
  - `src/mem_graph/tools/memory/conversation.py`
  - `src/mem_graph/tools/memory/memory.py`
  - `src/mem_graph/tools/memory/notes.py`
  - `src/mem_graph/tools/work/projects.py`
  - `src/mem_graph/tools/work/tasks.py`
  - `src/mem_graph/tools/work/decisions.py`
  - `src/mem_graph/tools/work/violations.py`

### Tests and docs

- Added `tests/test_visibility_discovery.py` covering:
  - pinned discovery tool surface
  - registry-driven agent listing
  - honest empty skill registry behavior
  - `system_inspect()` summary output
- Updated discovery docs:
  - `mcp_guide.md`
  - `docs/context/context_map.md`

## Final verification

- `PYTHONPATH=src uv run pytest -q` → **102 passed**
- `PYTHONPATH=src uv run ruff check .` → **clean**
- `PYTHONPATH=src uv run mypy .` → **clean**
