# Logfire Integration Tasklist

## Goal

Add Logfire as the live execution recorder for agents, tools, memory operations, and graph access so debugging and operational diagnosis do not rely on post-hoc log scraping alone.

Prerequisite: See `docs/planning/tasks/007-fastmcp-task.md` — Logfire can be added before or after 007; coordinate bootstrap so Logfire and FastMCP features align.

## Dependencies

- Should layer on top of the OpenTelemetry task rather than compete with it.
- Must respect existing logging behavior and avoid leaking sensitive prompt or graph data by default.
- Follow `docs/planning/design/015-logfire.md` and the target file plan in `docs/planning/design/FILE_STRUCTURE.md`.

## Work Envelope

- Planned new files: 2
- Planned file edits: 10-11
- Shape: edit-heavy, single task
- Why this size works: Logfire mostly threads through existing modules, so the work is broad instrumentation rather than file creation

## Planned Files

New files:
- `src/mem_graph/observability/logfire_setup.py`
- `src/mem_graph/services/memory.py`

Existing files to edit:
- `src/mem_graph/server.py`
- `src/mem_graph/db.py`
- `src/mem_graph/logging.py`
- `src/mem_graph/agents/__init__.py`
- `src/mem_graph/agents/orchestrator_agent.py`
- `src/mem_graph/agents/orchestrator_graph.py`
- `src/mem_graph/tools/agents/audit.py`
- `src/mem_graph/tools/memory/memory.py`
- `src/mem_graph/tools/filesystem/filesystem.py`
- `src/mem_graph/tools/work/violations.py`
- `docs/documentation/runbook.md`

## Tasklist

- [ ] Add a Logfire bootstrap module with environment-driven configuration and a safe no-token path for local development.
- [ ] Decide which operations log structured payload metadata versus redacted summaries so live traces stay useful without exposing too much content.
- [ ] Instrument graph access, memory operations, and the most important tool entry points with consistent Logfire scopes.
- [ ] Add Logfire-aware logging around orchestration and agent execution so long runs can be replayed in sequence.
- [ ] Introduce a memory service wrapper or adapter where that gives cleaner instrumentation than embedding logging directly inside raw tool functions.
- [ ] Document alert and search patterns for on-call use, including what to look for in failed runs.
- [ ] Verify the Logfire layer complements rather than duplicates OpenTelemetry spans.

## Out Of Scope

- Streaming Logfire output back into MCP clients
- Per-user Logfire project routing
- Long-term retention policy changes outside standard Logfire configuration

## Done When

- [ ] Core agent and tool activity is visible in Logfire timelines.
- [ ] Operators have a documented search and alert workflow.
- [ ] Sensitive payload handling is deliberate instead of accidental.
- [ ] Logfire and OpenTelemetry can run together without conflicting bootstrap paths.

## References

- `docs/planning/design/015-logfire.md`
- `docs/planning/design/012-otel.md`
- `docs/planning/design/FILE_STRUCTURE.md`
- `docs/planning/design/links.md`
- `https://ai.pydantic.dev/logfire/`
