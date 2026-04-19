# Podman Session Sandboxing

Mem-graph can run generated code and workflow implementation work inside a
rootless Podman session sandbox. The feature is disabled by default.

## Settings

Set `MEM_GRAPH_SANDBOX_ENABLED=true` to enable the sandbox path.

Important defaults:

- `MEM_GRAPH_SANDBOX_BACKEND=podman`
- `MEM_GRAPH_SANDBOX_IMAGE=python:3.14-slim`
- `MEM_GRAPH_SANDBOX_COMPOSE_FILE=docker-compose.sandbox.yml`
- `MEM_GRAPH_SANDBOX_ROOT=./data/sandbox`
- `MEM_GRAPH_SANDBOX_NETWORK=none`
- `MEM_GRAPH_SANDBOX_MEMORY=1g`
- `MEM_GRAPH_SANDBOX_CPUS=2`
- `MEM_GRAPH_SANDBOX_EXEC_TIMEOUT_SECONDS=30`
- `MEM_GRAPH_SANDBOX_SESSION_TTL_SECONDS=3600`

## Requirements

The implementation targets rootless Podman and is compatible with Podman 5.4.2.
Local development uses the Podman CLI with `podman compose`. The manager keeps
Podman command construction behind a small adapter so a socket/API backend can be
added later without changing workflow code.

## Lifecycle

Each workflow gets a fresh `session_id`. The manager creates:

```text
data/sandbox/sessions/{session_id}/repo
data/sandbox/sessions/{session_id}/workspace
data/sandbox/sessions/{session_id}/metadata.json
```

`repo` is a read-only source snapshot. `workspace` is a writable copy used by
agents and validation commands. CodeMode lazily provisions the container on the
first `execute` call for a session, then reuses the same container for later
calls with the same `session_id`.

## Security Defaults

The compose template mounts `/repo` read-only and `/workspace` read-write, sets
`network_mode: none`, drops capabilities, enables `no-new-privileges`, uses a
read-only root filesystem, and avoids host secret passthrough. Snapshot creation
excludes `.env`, databases, generated logs, caches, virtualenvs, and runtime
state.

## Merge Back

Workflow merge-back compares `/workspace` against the original snapshot and
copies only changed files into the host tree. If the host file changed since the
snapshot, merge-back is blocked with a conflict. Runtime files, caches, secrets,
database files, logs, and sandbox metadata are excluded.

## Tests

Unit tests do not require Podman:

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
  tests/test_workflow_sandbox_sessions.py \
  tests/test_workflow_sandbox_merge_back.py \
  -q
```

Podman integration tests should be guarded with `MEM_GRAPH_RUN_PODMAN_TESTS=1`
and a `podman` pytest marker before they are added.
