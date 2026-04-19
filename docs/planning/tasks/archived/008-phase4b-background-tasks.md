# Phase 4b Background Tasks Tasklist

## Goal

Move the long-running FastMCP operations into background execution so audit, map, triage, and orchestration return a task ID immediately, publish progress, and can be polled safely by clients.

Prerequisite: See `docs/planning/tasks/007-fastmcp-task.md` — complete FastMCP 3.0 readiness before enabling FastMCP-specific task features.

## Dependencies

- Build on the FastMCP completion work in `docs/planning/tasks/007-fastmcp-task.md`.
- Keep confirmation flows from `docs/planning/design/006-phase3-interactivity.md` compatible with task execution.
- Follow the target layout in `docs/planning/design/FILE_STRUCTURE.md` and the phase design in `docs/planning/design/008-phase4b-tasks.md`.

## Work Envelope

- Planned new files: 6
- Planned file edits: 7-8
- Shape: balanced, single task
- Why this size works: well below the 15 new-file cap and below the 10-20 edit ceiling for one implementation pass

## Planned Files

New files:
- `src/mem_graph/models/task.py`
- `src/mem_graph/services/task_queue.py`
- `src/mem_graph/tools/background/__init__.py`
- `src/mem_graph/tools/background/task_status.py`
- `src/mem_graph/tools/background/progress.py`
- `tests/test_task_queue.py`

Existing files to edit:
- `src/mem_graph/server.py`
- `src/mem_graph/tools/__init__.py`
- `src/mem_graph/tools/agents/__init__.py`
- `src/mem_graph/tools/agents/audit.py`
- `src/mem_graph/tools/agents/map.py`
- `src/mem_graph/tools/agents/triage.py`
- `src/mem_graph/tools/agents/orchestrator.py`
- `docs/documentation/tools.md`

## Tasklist

- [x] Add `TaskStatus`, `TaskProgress`, `TaskResult`, and `Task` models with timestamps, status transitions, and result payload shape.
- [x] Implement a bounded in-memory `TaskQueue` service with enqueue, status lookup, completion tracking, and queued-task cancellation.
- [x] Add a background tools namespace that exposes status and progress helpers without coupling status lookup to any one agent tool.
- [x] Convert the heavy tools to `task=True` and keep their synchronous behavior available inside the task worker function.
- [x] Standardize progress messages so every background task reports percentage, current step, and user-meaningful status text.
- [x] Add `get_task_status` and `cancel_task` endpoints that work for queued, running, completed, failed, and cancelled tasks.
- [x] Wire queue lifecycle setup into server startup and ensure shutdown behavior is explicit about unfinished tasks.
- [x] Add tests for queue ordering, concurrency limits, terminal status handling, and status polling responses.
- [x] Document client polling expectations, cancellation semantics, and the fact that task state is in-memory only.

## Out Of Scope

- Persistent task storage across server restarts
- WebSocket or push-based progress streaming
- Priority scheduling or multi-tenant fairness controls

## Done When

- [x] `audit_package`, `map_codebase`, `triage_violations`, and `orchestrate_codebase` return a task identifier instead of blocking.
- [x] Clients can poll a stable status API and receive progress updates until completion.
- [x] Cancellation is explicit and safe for queued tasks, with clear behavior for running tasks.
- [x] No existing fast-path tools are forced into background mode unnecessarily.

## References

- `docs/planning/design/008-phase4b-tasks.md`
- `docs/planning/design/006-phase3-interactivity.md`
- `docs/planning/design/FILE_STRUCTURE.md`
- `docs/planning/design/links.md`
