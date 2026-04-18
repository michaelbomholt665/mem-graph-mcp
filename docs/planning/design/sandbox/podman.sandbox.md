Here’s a compact, agent‑ready design document you can hand off as a research/planning spec for adding Podman‑backed “per‑session” sandboxing to your existing FastMCP 3 + CodeMode + Pydantic‑AI‑agents stack.

***

### 1. Goal

Add a **Podman‑backed sandbox layer** to your FastMCP 3 server so that:

- Each long‑running workflow (orchestrator → sub‑agents) runs inside a per‑session container.
- The container has a **snapshot of the codebase** mounted as a read‑only workspace.
- The MCP server’s `code_mode` runs untrusted generated code in that sandbox.
- Sub‑agents inside the workflow share the same session filesystem and can cooperate via files and artifacts.
- The container is strictly isolated and destroyed when the session ends.

***

### 2. Scope and non‑goals

- **Out of scope (not in this design)**
  - Changing the core FastMCP 3 protocol or Python SDK.
  - Re‑designing the Pydantic AI agent logic; just adapt how they talk to the MCP server.
  - Building a UI/CLI for the user; this is infra‑ and API‑only.

- **In scope**
  - Podman container lifecycle per session.
  - Session‑scoped workspace with repo snapshot.
  - Integration with FastMCP’s `code_mode` / `SandboxProvider`.
  - Safety, logging, and basic cleanup.

***

### 3. Architecture overview

Three layers:

1. **Orchestrator layer (Pydantic AI agents)**
   - The main agent acts as a workflow orchestrator.
   - It receives a `task_id` and optionally creates or reuses a `session_id`.
   - It delegates work to sub‑agents that in turn call tools via the MCP server.

2. **MCP server layer (FastMCP 3 + CodeMode)**
   - Exposes a `code_mode` endpoint that receives code and executes it in a sandbox.
   - Has a custom `SandboxProvider` implementation that delegates to a **Session‑Sandbox Manager**.

3. **Sandbox layer (Podman + Session manager)**
   - The **Session‑Sandbox Manager** owns a mapping:
     ```python
     session_id → (container_id, workspace_path, status, created_at, ...)
     ```
   - On first tool call for a session, it:
     - Starts a Podman container from a base image.
     - Mounts a **read‑only repo snapshot** and a **writable session scratch**.
   - Later calls reuse the same container for that `session_id`.
   - On workflow end or timeout, it destroys the container and cleans up mounts.

***

### 4. Session model

- **Session identity**
  - Each long‑running implementation workflow gets a `session_id` (UUID).
  - The `session_id` is passed implicitly via the MCP server context (e.g., as a header, context var, or part of the `tool_call` metadata).

- **Session lifecycle**
  1. `SessionCreated`:
     - Orchestrator starts a workflow.
     - MCP server sees a new `session_id` and asks the Session‑Sandbox Manager to provision a container.
  2. `SessionActive`:
     - All CodeMode tool calls for that `session_id` run inside the same container.
     - Sub‑agents can read/write files in the session workspace.
  3. `SessionEnded`:
     - Workflow finishes or times out.
     - MCP server notifies the Session‑Sandbox Manager to terminate the container.
     - Artifacts are archived (optional) and the session is marked as `terminated`.

***

### 5. Podman container setup

- **Image base**
  - A minimal Python image with the tools needed for your agents (e.g., shared utilities, linters, formatters, diff tools).
  - Prefer rootless, non‑privileged, and constrained (drop specific caps, no `--privileged`).

- **Volumes/mounts per session**
  - Read‑only repo snapshot:
    - Source: a recent snapshot of the target codebase (e.g., via `git worktree`, `rsync`, or `podman cp` at start).
    - Mount: `/repo:ro` inside the container.
    - Strategy:
      - Either snapshot once per repo and reuse it for many sessions, or per‑repo‑branch snapshot if needed.
  - Writable session workspace:
    - A dedicated scratch dir per `session_id` on the host, mounted as `/workspace:rw`.
    - Inside the container, sub‑agents write generated code, test outputs, and artifacts here.

- **Networking and security**
  - Default: no external network (`--network=none`) unless explicitly needed.
  - If sub‑agents need controlled access, use explicit allow‑lists or a sidecar proxy.
  - Apply `--security-opt` (e.g., `no‑new‑privs`) and resource limits (`--memory`, `--cpus`).

- **Environment**
  - Clear environment on start; only inject known variables.
  - Do **not** passthrough secrets; pass them via files or a secure secrets store.

***

### 6. Integration with FastMCP CodeMode

- **Implementation of `SandboxProvider`**
  - The MCP server mounts a custom `SandboxProvider` that doesn’t execute code directly.
  - Instead, it forwards the code payload, `session_id`, and necessary metadata to the **Session‑Sandbox Manager**.

- **Execution flow**
  1. CodeMode receives a code snippet `code` and context including `session_id`.
  2. `SandboxProvider` calls `SessionSandboxManager.run_in_session(session_id, code)`.
  3. The manager either:
     - Lazily starts a container for that session, or
     - Reuses the existing one.
  4. The code is executed inside the container (e.g., via `podman exec` or a small runner script).
  5. The manager returns `stdout`, `stderr`, exit code, and optionally captured artifacts.
  6. CodeMode returns that result to the Pydantic agent.

- **Error handling**
  - If the container fails or times out, the provider raises a sandbox‑specific error.
  - The orchestrator can decide to retry, abort, or start a fresh session.

***

### 7. Session‑Sandbox Manager (key responsibilities)

- **Container lifecycle**
  - `create_session(session_id, repo_ref, snapshot_path, ...)`:
    - Starts a Podman container with the right mounts.
    - Records `container_id` and `workspace_path`.
  - `run_in_session(session_id, code)`:
    - Executes code in the container, returns results.
  - `destroy_session(session_id)`:
    - Stops and removes the container, deletes scratch workspace, and removes the session from the registry.

- **Session registry**
  - A simple in‑memory or persistent registry mapping `session_id` to metadata.
  - Includes timestamps, resource limits, and a cleanup status.

- **Snapshot strategy**
  - Decide whether to:
    - Share one snapshot across many sessions (cheap, but stale).
    - Snapshot per repo‑branch or per workflow (fresh, more expensive).
  - Expose this as a config knob (e.g., `SNAPSHOT_POLICY = "per_repo" | "per_workflow"`).

***

### 8. Sub‑agent behavior in the sandbox

- **Shared workspace semantics**
  - All sub‑agents in the same session see the same `/workspace` and the same `/repo`.
  - They communicate via:
    - Files (e.g., `workspace/plan.json`, `workspace/patch.diff`).
    - Tool outputs already exposed by the MCP server.

- **No direct container control**
  - Sub‑agents should not call `podman` themselves.
  - Container control is entirely via the MCP server and Session‑Sandbox Manager.

***

### 9. Safety and isolation

- **Per‑session isolation**
  - Each workflow has its own container; no shared mutable filesystems.
  - If needed, add pod‑level security (e.g., SELinux, or user namespaces) depending on your Podman setup.

- **Resource limits**
  - Configure CPU, memory, and wall‑time limits per container.
  - The Session‑Sandbox Manager enforces timeouts and kills hanging containers.

- **Cleanup guarantees**
  - Use context managers and deferred cleanup (e.g., `try/finally` around session workflow).
  - Add a periodic cleanup job that kills stale containers whose sessions have expired.

***

### 10. Failure modes and recovery

- **Agent or tool failure**
  - Let the MCP server expose structured errors; the orchestrator can retry or abort.
  - Do not restart the container for transient errors; reuse the same session unless the state is corrupted.

- **Container crash / OOM**
  - The Session‑Sandbox Manager detects failure and marks the session as `failed`.
  - The orchestrator can decide to start a new session and retry the workflow.

- **Timeouts**
  - Set hard timeouts at both:
    - Session level (total workflow time).
    - Single tool call level (e.g., 10–30 seconds per `code` execution).

***

### 11. Logging and observability

- **Structured logs**
  - Tag all logs with `session_id`, `agent_type`, and `step_id`.
  - Capture container logs and map them to the session.

- **Metrics**
  - Count sessions created/destroyed, avg lifetime, pod count per host, resource usage.
  - Alert on stuck containers or leaked sessions.

***

### 12. Optional extensions

- **Checkpoint‑style snapshots (advanced)**
  - For very long workflows, consider using Podman’s checkpoint/restore (if available in your setup) to capture container state at key milestones.
  - This is heavier than filesystem snapshots and should be opt‑in.

- **Session reuse across short workflows**
  - If you ever want to cache environments, you can introduce a “session pool” that reuses idle containers for a short time, but with strict TTL and workspace reset.

***

### 13. Concrete next‑step questions for your AI agent

Ask your agent to research and answer:

1. Given our current FastMCP 3 setup and CodeMode, how should the `SandboxProvider` interface be implemented to delegate to Podman?
2. What is the best Podman‑specific pattern for starting a container with rootless, non‑privileged, and controlled mounts?
3. How should we design the in‑memory vs persistent session registry (SQL, in‑memory, Redis, etc.)?
4. Which repo snapshot strategy (`per_repo`, `per_branch`, `per_workflow`) is most appropriate for our typical workflow length and concurrency?
5. How should we handle secrets and environment variables so that the sandbox never accidentally inherits host secrets?

***

You can paste this document to your agent almost verbatim and tell it:
> “Use this as a spec. Research each numbered section, propose concrete code interfaces, and draft a migration plan for integrating this sandbox layer into our existing FastMCP 3 + CodeMode + Pydantic‑AI‑agents stack.”
