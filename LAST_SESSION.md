# Last Session Summary

**Date:** 2026-04-19  
**Task:** 028 — Podman-Backed Per-Session Sandboxing

## What Changed

Implemented the first end-to-end sandbox layer for workflow and CodeMode paths:

- Added `src/mem_graph/sandbox/` with typed settings, models, errors, snapshot/workspace management, Podman compose argv construction, a Podman adapter, session lifecycle manager, cleanup helpers, and a FastMCP CodeMode provider.
- Added `docker-compose.sandbox.yml` for one rootless, non-privileged, no-network-by-default sandbox container per session.
- Added per-session layout under `data/sandbox/sessions/{session_id}/` with read-only repo snapshots, writable workspaces, and metadata persistence.
- Added lazy container provisioning on first execution, per-session locking, structured execution results, timeout/output-cap plumbing, crash/OOM state handling, idempotent destroy, stale cleanup, and metadata recovery.
- Added merge-back support that compares workspace changes against the original snapshot, excludes runtime/secrets/cache/database files, and blocks host conflicts.
- Added `WorkflowSandboxPolicy` to workflow resources and propagated selected sandbox policy through `WorkflowSelection`.
- Added profile defaults for small, medium, and large workflow sandbox policies.
- Added workflow runtime helpers in `workflow_sandbox.py` for create/finalize/abort lifecycle handling.
- Integrated sandbox creation/finalization into autopilot and managed workflow runtimes, with optional session artifacts added to runtime state.
- Made package audit sandbox behavior explicit: read-only dry-run audits stay unsandboxed; `execute_agents=True` can create a sandbox but never merges back.
- Added sandbox admin MCP tools for status, list, and destroy under the lazy `sandbox` namespace.
- Wired the sandbox manager into server startup/shutdown and enabled a session-aware CodeMode transform when `MEM_GRAPH_SANDBOX_ENABLED=true`.
- Documented settings, Podman 5.4.2/rootless assumptions, lifecycle, security defaults, merge-back, and test commands in `docs/documentation/sandbox.md`.

## Tests Added

- `tests/test_sandbox_config.py`
- `tests/test_sandbox_podman.py`
- `tests/test_sandbox_snapshots.py`
- `tests/test_sandbox_manager.py`
- `tests/test_sandbox_provider.py`
- `tests/test_workflow_sandbox_sessions.py`
- `tests/test_workflow_sandbox_merge_back.py`
- Additional sandbox policy assertions in `tests/test_agent_workflows.py`

## Verification

- `MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true .venv/bin/pytest tests/test_sandbox_config.py tests/test_sandbox_podman.py tests/test_sandbox_snapshots.py tests/test_sandbox_manager.py tests/test_sandbox_provider.py tests/test_agent_workflows.py tests/test_workflow_sandbox_sessions.py tests/test_workflow_sandbox_merge_back.py -q`  
  Result: **56 passed**
- `MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true .venv/bin/pytest tests/test_sandbox_config.py tests/test_sandbox_podman.py tests/test_sandbox_snapshots.py tests/test_sandbox_manager.py tests/test_sandbox_provider.py tests/test_agent_workflows.py tests/test_workflow_sandbox_sessions.py tests/test_workflow_sandbox_merge_back.py tests/test_agent_update.py -q`  
  Result: **64 passed**
- `MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true .venv/bin/pytest tests/test_audit.py tests/test_db.py tests/test_decision_agent.py tests/test_diagram_agent.py tests/test_evals.py tests/test_jina_embedder.py tests/test_logfire_setup.py tests/test_map_agent.py tests/test_parsers.py tests/test_server_metadata.py tests/test_task_agent.py tests/test_triage_agent.py -q`  
  Result: **30 passed, 1 failed** (`tests/test_logfire_setup.py::test_logfire_setup_uses_safe_defaults`, pre-existing Logfire HTTPX instrumentation expectation)
- `MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true .venv/bin/pytest tests/test_filesystem_tools.py tests/test_filesystem_tree.py tests/test_task_queue.py tests/test_tools.py -vv`  
  Result: **38 passed**
- `MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true .venv/bin/pytest tests/test_document_evals.py tests/test_fix_evals.py tests/test_graph.py tests/test_jina.py tests/test_map_evals.py tests/test_openapi_provider.py tests/test_report_writer.py tests/test_scorers.py tests/test_validate_evals.py tests/test_violation_writer.py tests/test_visibility_discovery.py -q`  
  Result: **25 passed**
- `.venv/bin/ruff check src tests`  
  Result: **clean**
- `.venv/bin/mypy src`  
  Result: **clean** (`184 source files`)

## Notes

- The implementation uses the Podman CLI and `podman compose` as the supported local/dev compose runner.
- The FastMCP sandbox provider interface in the installed version is `run(code, inputs=None, external_functions=None)`. The project now uses a `SessionCodeMode` wrapper so `ctx.session_id` is forwarded into the provider.
- No raw code payloads, prompts, secrets, or raw execution parameters are logged by the sandbox lifecycle path.
- Full `pytest -q` was attempted, but one run without a timeout hung in the pre-existing async file-read path before fixes and a later timeout run expired. The covered batches above exercise the task-plan files plus the remaining repository tests except for the known Logfire assertion.
