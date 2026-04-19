# Task 028: Podman-Backed Per-Session Sandboxing

**Status:** Complete  
**Priority:** High  
**Blocked by:** None  
**Blocks:** Safe generated-code execution, isolated multi-agent workflow workspaces, and sandboxed command execution

**Workflow baseline:** Task 026 has implemented Python-first workflow resources and runtime modules. Sandbox work should integrate with those modules directly instead of adding a separate workflow system.

## Problem Statement

Generated code execution and long-running multi-agent workflows need an isolation boundary that is stronger than process-level execution on the host.

Add a Podman-backed sandbox layer where each workflow session gets its own rootless container, read-only codebase snapshot, and writable session workspace. CodeMode and workflow sub-agents should reuse the same session container so agents can cooperate through files while still being isolated from the host and from other sessions.

## Goals

1. Add a session sandbox manager that owns Podman container lifecycle per `session_id`.
2. Provide read-only repo snapshots and writable per-session workspaces.
3. Integrate the manager with FastMCP CodeMode through a custom sandbox provider path.
4. Pass session context consistently from orchestrator/workflow entry points into tool execution.
5. Run generated code inside the session container and return structured execution results.
6. Enforce rootless, non-privileged, resource-limited, no-network-by-default containers.
7. Add cleanup for explicit session end, timeout, and stale/leaked containers.
8. Add observability without logging raw code payloads, secrets, or raw execution parameters.

## Non-Goals

- No FastMCP protocol redesign.
- No rewrite of Pydantic AI agent logic beyond session-context plumbing.
- No user-facing UI or CLI for sandbox control.
- No direct Podman access for sub-agents.
- No broad host shell execution escape hatch.
- No secret passthrough into containers by default.
- No container pooling until the single-session lifecycle is proven.

## Target Architecture

```text
src/mem_graph/
  sandbox/
    __init__.py
    config.py
    errors.py
    models.py
    podman.py
    snapshots.py
    manager.py
    cleanup.py
    provider.py
    compose.py
  services/
    sandbox_sessions.py
  tools/
    sandbox/
      __init__.py
      session.py
```

Likely integration points:

```text
src/mem_graph/server.py
src/mem_graph/app/lifespan.py
src/mem_graph/resources/workflows/models.py
src/mem_graph/resources/workflows/profiles.py
src/mem_graph/resources/workflows/selector.py
src/mem_graph/tools/agents/orchestrator.py
src/mem_graph/workflows/runtime/orchestrator_runtime.py
src/mem_graph/workflows/runtime/managed_workflow_runtime.py
src/mem_graph/workflows/runtime/package_audit_runtime.py
src/mem_graph/workflows/runtime/workflow_sandbox.py
src/mem_graph/services/command_shell.py
src/mem_graph/services/command_parse_stage.py
docker-compose.sandbox.yml
```

The compose file is a sandbox service template. The session manager should start it with a unique project name per task/session, not as one shared long-lived environment.

## Session Model

Each long-running workflow receives a UUID `session_id`. The same `session_id` is propagated through orchestration, sub-agent tool calls, and CodeMode execution.

Session states:

| State | Meaning |
|---|---|
| `created` | Session metadata exists but the container may not be provisioned yet. |
| `active` | Container exists and accepts executions. |
| `failed` | Container crashed, timed out, or failed health checks. |
| `terminating` | Cleanup is in progress. |
| `terminated` | Container and workspace cleanup completed. |

Session metadata should include:

- `session_id`
- `container_id`
- `repo_ref`
- `snapshot_path`
- `workspace_path`
- `status`
- `created_at`
- `last_used_at`
- `expires_at`
- CPU, memory, network, and timeout policy
- cleanup/error details

## Configuration

Add typed settings for the sandbox layer.

Initial environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `MEM_GRAPH_SANDBOX_ENABLED` | `false` | Feature flag for Podman sandbox execution. |
| `MEM_GRAPH_SANDBOX_BACKEND` | `podman` | Sandbox backend selector. |
| `MEM_GRAPH_SANDBOX_IMAGE` | project default image | Container image for sessions. |
| `MEM_GRAPH_SANDBOX_COMPOSE_FILE` | `docker-compose.sandbox.yml` | Compose template used to start per-task sandbox containers. |
| `MEM_GRAPH_SANDBOX_ROOT` | `./data/sandbox` | Host root for snapshots and workspaces. |
| `MEM_GRAPH_SANDBOX_SNAPSHOT_POLICY` | `per_workflow` | `per_repo`, `per_branch`, or `per_workflow`. |
| `MEM_GRAPH_SANDBOX_NETWORK` | `none` | Default Podman network mode. |
| `MEM_GRAPH_SANDBOX_MEMORY` | `1g` | Container memory limit. |
| `MEM_GRAPH_SANDBOX_CPUS` | `2` | Container CPU limit. |
| `MEM_GRAPH_SANDBOX_EXEC_TIMEOUT_SECONDS` | `30` | Single execution timeout. |
| `MEM_GRAPH_SANDBOX_SESSION_TTL_SECONDS` | `3600` | Session lifetime before stale cleanup. |
| `MEM_GRAPH_SANDBOX_CLEANUP_INTERVAL_SECONDS` | `300` | Periodic stale cleanup interval. |

## Implementation Phases

### Phase 1: Research and Interface Confirmation

- [x] Confirm the exact FastMCP CodeMode sandbox provider interface available in the installed version.
- [x] Identify how `execute` receives request context, headers, or metadata.
- [x] Decide where `session_id` should live in server context.
- [x] Confirm whether existing workflow runtime from Task 026 is ready to pass session metadata.
- [x] Document the minimum Podman version and rootless requirements.
- [x] Confirm support for Podman 5.4.2.
- [x] Decide whether the first implementation uses the Podman CLI or Podman socket/API.
- [x] Decide whether `podman compose` or `podman-compose` is the supported compose runner in local/dev environments.

Decision target:

- Prefer a small Podman adapter boundary so the manager is not coupled to CLI argument construction.
- Use no-network rootless containers by default.
- Use one compose project per task/session so every task starts with a fresh container.

### Phase 2: Sandbox Models, Config, and Errors

- [x] Add `src/mem_graph/sandbox/config.py` with Pydantic settings.
- [x] Add `src/mem_graph/sandbox/models.py` for session metadata and execution results.
- [x] Add `src/mem_graph/sandbox/errors.py` with typed sandbox exceptions.
- [x] Add feature-flag behavior for disabled sandbox mode.
- [x] Add tests for settings defaults and env overrides.

Core models:

- [x] `SandboxSession`
- [x] `SandboxStatus`
- [x] `SandboxResourceLimits`
- [x] `SandboxExecutionRequest`
- [x] `SandboxExecutionResult`
- [x] `SandboxPolicy`

### Phase 3: Podman Adapter

- [x] Add `src/mem_graph/sandbox/podman.py`.
- [x] Add `src/mem_graph/sandbox/compose.py`.
- [x] Add `docker-compose.sandbox.yml` as the default sandbox service template.
- [x] Build Podman command arguments without `shell=True`.
- [x] Start compose with a unique project name derived from `session_id`.
- [x] Pass snapshot/workspace paths through generated env files or explicit environment.
- [x] Implement container create/start with:
  - [x] rootless-compatible defaults
  - [x] `--network=none`
  - [x] `--security-opt=no-new-privileges`
  - [x] memory limit
  - [x] CPU limit
  - [x] read-only `/repo`
  - [x] writable `/workspace`
  - [x] minimal environment allowlist
- [x] Implement `exec` with timeout, output caps, and exit code capture.
- [x] Implement stop/remove with idempotent cleanup.
- [x] Implement inspect/health status checks.
- [x] Implement compose down/remove for the session project.
- [x] Add unit tests that assert argv construction and policy enforcement.
- [x] Add integration tests gated behind a `podman` marker or env flag.

Security requirements:

- [x] Forbid `--privileged`.
- [x] Forbid host network by default.
- [x] Forbid host secret/env passthrough.
- [x] Do not invoke a shell for Podman commands.
- [x] Validate mount paths are under configured sandbox roots.

Compose-file requirements:

- [x] Define a single sandbox service for agent/code execution.
- [x] Mount the session repo snapshot read-only at `/repo`.
- [x] Mount the session workspace read-write at `/workspace`.
- [x] Ensure `/workspace` is a writable working copy for agents that modify code.
- [x] Set `working_dir` to `/workspace`.
- [x] Disable networking by default.
- [x] Drop privileges and use `no-new-privileges`.
- [x] Avoid privileged mode and host PID/IPC/network namespaces.
- [x] Use explicit CPU and memory limits where supported by the compose runner.
- [x] Use only an allowlisted environment, with no host secret passthrough.
- [x] Keep the container alive for repeated per-session `exec` calls.
- [x] Label containers with `mem_graph.session_id` and cleanup metadata.
- [x] Avoid hard-coded host paths; all host paths come from session manager variables.

### Phase 4: Snapshot and Workspace Management

- [x] Add `src/mem_graph/sandbox/snapshots.py`.
- [x] Add per-session workspace directory creation under `MEM_GRAPH_SANDBOX_ROOT`.
- [x] Add repo snapshot creation for the initial policy.
- [x] Initialize the writable workspace from the repo snapshot for implementation workflows.
- [x] Support `per_workflow` snapshots first.
- [x] Design but defer shared `per_repo` and `per_branch` cache invalidation if needed.
- [x] Ensure snapshot paths and workspace paths are never user-controlled raw paths.
- [x] Preserve file modes needed for test and tool execution.
- [x] Exclude `.env`, database files, generated logs, and other sensitive/runtime files.
- [x] Add cleanup helpers for workspaces and snapshots.
- [x] Add tests for snapshot filtering and directory layout.

Initial host layout:

```text
data/sandbox/
  sessions/
    {session_id}/
      repo/
      workspace/
      metadata.json
```

Container mounts:

```text
/repo       read-only snapshot
/workspace  read-write working copy and session scratch
```

Per-task flow:

1. Create a fresh `session_id` for the task.
2. Snapshot the current codebase into that session.
3. Initialize `/workspace` as a writable working copy from the snapshot.
4. Start a new compose project/container for that session.
5. Run all workflow agents inside the sandbox container.
6. Validate changes inside the sandbox.
7. If tests pass and the workflow accepts the result, merge the sandbox workspace changes back into the host codebase.
8. Stop and delete the compose project/container.
9. Delete the session workspace/snapshot unless artifact retention is enabled.

### Phase 5: Session Sandbox Manager

- [x] Add `src/mem_graph/sandbox/manager.py`.
- [x] Implement `create_session(session_id, repo_ref, policy)`.
- [x] Implement lazy container provisioning on first execution.
- [x] Implement `run_in_session(session_id, request)`.
- [x] Implement `destroy_session(session_id)`.
- [x] Implement container crash/OOM detection and `failed` state transition.
- [x] Add an in-memory registry for the first version.
- [x] Persist enough metadata to recover and clean up stale containers after process restart.
- [x] Add lock protection so concurrent calls for one session do not race container creation.
- [x] Add output caps and timeout handling.
- [x] Add tests for lifecycle transitions.
- [x] Add tests for concurrent first-use creation.

Registry policy:

- First implementation should use in-memory state plus metadata files under the sandbox root.
- Revisit Redis or DB-backed registry only if multi-process/multi-host orchestration becomes required.

### Phase 6: Cleanup Lifecycle

- [x] Add `src/mem_graph/sandbox/cleanup.py`.
- [x] Hook sandbox manager startup/shutdown into FastMCP app lifespan.
- [x] Add periodic stale-session cleanup.
- [x] Stop and remove containers on explicit workflow completion.
- [x] Stop and remove containers after session TTL.
- [x] Clean workspaces after successful termination unless artifact retention is enabled.
- [x] Mark cleanup failures in metadata for later retry.
- [x] Add tests for idempotent cleanup.

Cleanup guarantees:

- Session termination should be best-effort but repeatable.
- Cleanup must not delete paths outside `MEM_GRAPH_SANDBOX_ROOT`.

### Phase 7: FastMCP CodeMode Integration

- [x] Add `src/mem_graph/sandbox/provider.py`.
- [x] Implement the custom sandbox provider that delegates to `SessionSandboxManager`.
- [x] Wire the provider in `src/mem_graph/server.py` behind `MEM_GRAPH_SANDBOX_ENABLED`.
- [x] Ensure CodeMode passes `session_id` to the provider.
- [x] Return structured results with stdout, stderr, exit code, timeout flag, and artifact metadata.
- [x] Convert sandbox failures into stable MCP/tool error shapes.
- [x] Add tests for success, nonzero exit, timeout, and missing session context.

Execution contract:

```json
{
  "stdout": "...",
  "stderr": "...",
  "exit_code": 0,
  "timed_out": false,
  "artifacts": []
}
```

### Phase 8: Workflow and Sub-Agent Session Propagation

Task 026 created the active workflow integration surface:

- `src/mem_graph/resources/workflows/models.py`
- `src/mem_graph/resources/workflows/profiles.py`
- `src/mem_graph/resources/workflows/selector.py`
- `src/mem_graph/workflows/runtime/orchestrator_runtime.py`
- `src/mem_graph/workflows/runtime/managed_workflow_runtime.py`
- `src/mem_graph/workflows/runtime/package_audit_runtime.py`
- `src/mem_graph/tools/agents/orchestrator.py`

Add sandbox creation and cleanup to that path.

#### Phase 8A: Workflow Resource Sandbox Policy

- [x] Add a typed sandbox policy model to workflow resources, e.g. `WorkflowSandboxPolicy`.
- [x] Add sandbox policy fields to `WorkflowProfile` or `WorkflowResource` without breaking existing constructors.
- [x] Define profile defaults in `profiles.py`:
  - [x] `small`: sandbox enabled for code-writing workflows, short TTL, low resource limits.
  - [x] `medium`: sandbox enabled, standard TTL, moderate resource limits.
  - [x] `large`: sandbox enabled, longer TTL, checkpoint/cleanup metadata.
- [x] Add selector output fields so `WorkflowSelection` carries the chosen sandbox policy.
- [x] Add tests in `tests/test_agent_workflows.py` for sandbox policy defaults and selector propagation.

#### Phase 8B: Workflow Sandbox Runtime Helper

- [x] Add `src/mem_graph/workflows/runtime/workflow_sandbox.py`.
- [x] Implement `ensure_workflow_sandbox(selection, task_context)` to create a fresh `session_id` per task when sandboxing is enabled.
- [x] Implement `start_workflow_sandbox(...)` to call `SessionSandboxManager.create_session(...)`.
- [x] Implement `finalize_workflow_sandbox(...)` to validate, merge back when allowed, and destroy the session.
- [x] Implement `abort_workflow_sandbox(...)` to destroy the session without merge-back.
- [x] Provide a no-op implementation when `MEM_GRAPH_SANDBOX_ENABLED=false`.
- [x] Ensure all helper APIs are testable with a fake sandbox manager.

#### Phase 8C: Orchestrator Runtime Integration

- [x] Update `orchestrator_runtime.py` so `autopilot_graph_run_with_selection()` creates a sandbox before implementation work starts.
- [x] Store `session_id`, `workspace_path`, and sandbox status in runtime state/artifacts.
- [x] Ensure implementation and validation steps execute against the sandbox workspace.
- [x] Add `try/finally` cleanup so failed runs still destroy the sandbox.
- [x] Ensure successful validation triggers merge-back before cleanup.
- [x] Ensure failed validation blocks merge-back and preserves failure metadata.

#### Phase 8D: Managed Workflow Runtime Integration

- [x] Update `managed_workflow_runtime.py` so `run_managed_workflow_with_selection()` creates one sandbox per task/run.
- [x] Propagate `session_id` to sub-agent calls.
- [x] Ensure sub-agent command/file operations target `/workspace` through CodeMode or sandbox-aware services.
- [x] Add sandbox-aware retry behavior: retries reuse the same sandbox unless the session is marked corrupted/failed.
- [x] Destroy the sandbox at workflow completion, timeout, or abort.

#### Phase 8E: Package Audit Runtime Integration

- [x] Decide whether `package_audit` always uses a sandbox or only when `execute_agents=True`.
- [x] For sandboxed audits, mount the snapshot and run file reads from `/repo` or `/workspace` consistently.
- [x] Keep read-only audit workflows from merging back unless an explicit fix/remediation stage runs.
- [x] Add package-audit tests proving sandbox creation does not change chunking, dedup, or ranking behavior.

#### Phase 8F: Orchestrator Tool Integration

- [x] Update `src/mem_graph/tools/agents/orchestrator.py` to report sandbox creation in tool progress messages.
- [x] Include `session_id`, sandbox status, and merge-back status in returned task artifacts.
- [x] Keep existing tool response shapes stable by adding optional fields only.
- [x] Add tests that `autopilot_remediate` and `run_subagent_workflow` pass sandbox policy/session data into runtime calls.

#### Phase 8G: Merge-Back Workflow Step

- [x] Implement a merge-back service that compares sandbox `/workspace` to the original snapshot.
- [x] Use patch-based or Git-worktree-based merge-back; do not blindly copy the whole workspace over the host tree.
- [x] Exclude runtime files, caches, virtualenvs, databases, logs, secrets, and sandbox metadata.
- [x] Detect conflicts with host changes made after the sandbox snapshot.
- [x] Block merge-back on conflicts unless an explicit conflict-resolution policy is added.
- [x] Record changed files, validation command results, and merge-back status in workflow artifacts.
- [x] Add tests for clean merge, failed validation, conflict detection, and excluded files.

Shared workspace semantics:

- All sub-agents in one workflow session share `/workspace`.
- All sub-agents read the same `/repo` snapshot.
- Sub-agents may communicate through files in `/workspace`.
- Sub-agents must not control Podman directly.
- Host codebase changes occur only through the explicit merge-back step after validation.
- Every task/run gets a fresh sandbox container and fresh workspace.

### Phase 9: Optional Sandbox Session Tools

Add operational tools only if they are needed for debugging or automated cleanup.

- [x] Add `sandbox_session_status`.
- [x] Add `sandbox_session_list`.
- [x] Add `sandbox_session_destroy`.
- [x] Restrict destructive session tools behind the existing safety/confirmation pattern.
- [x] Keep these tools administrative; do not expose raw Podman controls.

### Phase 10: Observability and Audit Events

- [x] Add structured logs tagged with `session_id`, `container_id`, `workflow_id`, and `step_id`.
- [x] Record create/destroy/exec duration metrics.
- [x] Record timeout, crash, OOM, and cleanup-failure counters.
- [x] Ensure raw code snippets, raw prompts, raw tool payloads, secrets, and raw environment variables are not logged.
- [x] Add audit events for sandbox lifecycle transitions.
- [x] Add tests or assertions around log redaction where practical.

### Phase 11: Documentation

- [x] Document sandbox settings in project docs.
- [x] Document Podman rootless setup assumptions.
- [x] Document session lifecycle and cleanup behavior.
- [x] Document how to run Podman-gated integration tests.
- [x] Document the default no-network policy and how controlled network access would be added later.

## Acceptance Criteria

- A workflow can create or reuse a `session_id`.
- First CodeMode execution for a session lazily provisions a Podman container.
- Later CodeMode executions for the same session reuse the same container and workspace.
- `/repo` is mounted read-only and `/workspace` is mounted read-write.
- A `docker-compose.sandbox.yml` template exists and is used to start one fresh sandbox project per task/session.
- `WorkflowSelection` carries a sandbox policy selected from the Python-first workflow resources.
- `autopilot_graph_run_with_selection()` creates, uses, finalizes, and cleans up a sandbox for implementation workflows.
- `run_managed_workflow_with_selection()` creates one sandbox per managed workflow run and propagates the session to sub-agents.
- `package_audit` sandbox behavior is explicit and covered by tests.
- Containers run rootless/non-privileged with no external network by default.
- Resource limits and per-exec timeouts are enforced.
- Agents execute implementation work inside the sandbox workspace.
- Passing sandbox changes can be merged back into the host codebase through an explicit workflow step.
- Failed sandbox validation prevents merge-back.
- Execution results include stdout, stderr, exit code, timeout status, and artifact metadata.
- Explicit session end removes the container and cleans up the workspace.
- Stale sessions are cleaned up by a periodic job.
- Disabled sandbox mode keeps existing non-sandbox behavior working.
- Tests cover lifecycle, config, argv safety, timeout handling, cleanup, and session propagation.

## Test Plan

Unit tests:

```bash
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present \
MEM_GRAPH_LOGFIRE_ENABLED=false \
OTEL_SDK_DISABLED=true \
uv run pytest \
  tests/test_sandbox_config.py \
  tests/test_sandbox_podman.py \
  tests/test_sandbox_snapshots.py \
  tests/test_sandbox_manager.py \
  tests/test_sandbox_provider.py \
  -q
```

Workflow/session propagation tests:

```bash
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present \
MEM_GRAPH_LOGFIRE_ENABLED=false \
OTEL_SDK_DISABLED=true \
uv run pytest \
  tests/test_agent_workflows.py \
  tests/test_workflow_sandbox_sessions.py \
  tests/test_workflow_sandbox_merge_back.py \
  -q
```

Podman integration tests, gated by an explicit marker/env flag:

```bash
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present \
MEM_GRAPH_LOGFIRE_ENABLED=false \
OTEL_SDK_DISABLED=true \
MEM_GRAPH_RUN_PODMAN_TESTS=1 \
uv run pytest -m podman tests/test_sandbox_podman_integration.py -q
```

Regression gate:

```bash
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present \
MEM_GRAPH_LOGFIRE_ENABLED=false \
OTEL_SDK_DISABLED=true \
uv run pytest -q
uv run ruff check src tests
uv run mypy src
```

## Open Questions

1. Which FastMCP CodeMode sandbox provider hooks are available in the installed FastMCP version?
2. Should the first Podman implementation use the CLI or Podman socket/API?
3. Should local/dev use `podman compose` or `podman-compose`?
4. Should merge-back be patch-based, rsync-based with exclusions, or Git worktree based?
5. Should artifacts be deleted by default, retained for a short TTL, or archived into graph memory metadata?
6. Is `per_workflow` snapshotting acceptable for expected workflow duration and concurrency, or should `per_branch` caching be implemented early?
7. Do any workflow categories require controlled network access, and if so should that be a separate opt-in policy profile?
8. Should session metadata eventually live in Ladybug, or is filesystem metadata sufficient until multi-process orchestration exists?

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Leaked containers or workspaces | Periodic cleanup, metadata recovery, idempotent destroy. |
| Host secret exposure | Clear environment, snapshot exclusions, no default secret mounts. |
| Container breakout risk | Rootless Podman, no privileged mode, no host network, constrained mounts. |
| Race on first session use | Per-session async lock around provisioning. |
| Stale repo snapshots | Start with `per_workflow`; add cache invalidation only after measuring cost. |
| Slow tests without Podman | Keep Podman integration tests gated; unit-test adapter argv and manager behavior with fakes. |
| Excessive logs | Structured lifecycle logs only; never log raw code or prompts. |

## Deferred Extensions

- Shared snapshot cache for `per_repo` and `per_branch`.
- Controlled egress through an allowlisted proxy.
- Session pools for short workflows.
- Podman checkpoint/restore for long workflows.
- Artifact archival into memory graph nodes.
- Multi-host sandbox scheduling.
