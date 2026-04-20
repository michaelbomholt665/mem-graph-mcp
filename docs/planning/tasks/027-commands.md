# Task 027: Curated CLI Commands via CodeMode Execute

**Status:** Implemented
**Priority:** High
**Blocked by:** Task 026 for final `workflow start` implementation details
**Blocks:** oh-my-pi/custom CLI command rollout

## Problem Statement

The MCP tool catalog is already large. Routine operations should not require repeated tool searches, schema inspection, and ad hoc tool-call planning.

Add a curated command layer for custom CLIs, including oh-my-pi, where commands trigger the running mem-graph server through the existing CodeMode `execute` tool. Do not add one MCP tool per command.

## Goals

1. Wire and verify CodeMode `execute` against the running MCP server.
2. Define a stable command result envelope for CLI output.
3. Add command templates for toolchain, agent, workflow, parser, embedding, DB, eval, lint, Python, and shell operations.
4. Prefer existing MCP tools through `call_tool(...)`.
5. Add importable support modules only for gaps not covered by existing tools.
6. Replace raw Cypher as the normal DB path with named query templates.
7. Add parser staging so automatic parsing does not immediately push every file change into the graph DB.

## Non-Goals

- No new command-specific MCP tools.
- No new `commands` or `execution` MCP namespace.
- No public broad shell execution tool.
- No final orchestrator implementation before Task 026 lands.
- No full oh-my-pi implementation in this task unless done as a thin reference adapter.

## Command Catalog

| Command | Description |
|---|---|
| `toolchain go` | Format, test, and scan a Go project. |
| `toolchain python` | Fix, typecheck, test, and scan this Python project. |
| `toolchain security` | Run cross-language security scanners. |
| `agent audit` | Run audit-category agents. |
| `agent map` | Run map/category discovery agents. |
| `agent fix` | Run fix/remediation agents. |
| `agent validate` | Run validation agents. |
| `agent document` | Run documentation and memory-update agents. |
| `workflow start` | Run the profile-selected multi-agent workflow. |
| `code parse` | Parse code with tree-sitter. |
| `code watch` | Watch code changes and stage parser output. |
| `code stage` | Stage parser output without DB ingest. |
| `code commit-index` | Commit staged parser output to the graph DB. |
| `embed documents` | Embed document/text content. |
| `embed code` | Embed code files or symbols. |
| `db migrate` | Run idempotent DB bootstrap/migration. |
| `db inspect` | Run predefined graph inspection templates. |
| `db query-template` | Run a named Cypher template with typed params. |
| `db cypher` | Run gated raw Cypher for debugging. |
| `eval gate` | Run fixture/CI/live/release eval gates. |
| `lint fix` | Run Ruff fix/check and mypy. |
| `python repl` | Run a CodeMode Python diagnostic snippet. |
| `shell execute` | Run a gated allowlisted shell command. |

## Target Files

Likely additions:

```text
src/mem_graph/services/commands/command_db.py
src/mem_graph/services/commands/command_shell.py
src/mem_graph/services/commands/command_evals.py
src/mem_graph/services/commands/command_parse_stage.py
src/mem_graph/services/commands/command_embed.py
src/mem_graph/services/commands/base.py
src/mem_graph/services/commands/catalog.py
```

Likely modifications:

```text
src/mem_graph/server.py
src/mem_graph/db.py
src/mem_graph/evals/evaluator.py
src/mem_graph/app/parsers/pipeline.py
src/mem_graph/app/parsers/ingest.py
src/mem_graph/sandbox/provider.py
docs/planning/design/016-commands-codemode.md
```

Optional reference adapter:

```text
scripts/mem_graph_commands/
tests/commands/
```

## Implementation Phases

### Phase 1: CodeMode Execute Wiring

- [x] DONE: Add or verify FastMCP CodeMode transform in `src/mem_graph/server.py`.
- [x] DONE: Confirm `execute` can call `get_server_info`.
- [x] DONE: Confirm `execute` can activate lazy namespaces with `tools_activate`.
- [x] DONE: Confirm `execute` can call existing parser and agent tools.
- [x] DONE: Document the exact MCP request shape expected by external CLIs.

### Phase 2: Command Result Contract

- [x] DONE: Define the JSON result envelope for all CLI command snippets.
- [x] DONE: Add reference snippet templates for common success and error responses.
- [x] DONE: Ensure task-returning commands preserve `task_id`, `poll_with`, and `cancel_with`.

### Phase 3: DB Command Support

- [x] DONE: Add `command_db.py`.
- [x] DONE: Add named DB query templates for common graph inspection.
- [x] DONE: Add typed parameter validation for templates.
- [x] DONE: Add `db inspect` template set, including schema counts and index status.
- [x] DONE: Add `db query-template` support.
- [x] DONE: Add gated `db cypher` raw-debug support.
- [x] DONE: Add idempotent `db migrate`/schema status helpers in `db.py` or `command_db.py`.

Initial DB templates:

- [x] DONE: `schema.counts`
- [x] DONE: `schema.indexes`
- [x] DONE: `projects.list`
- [x] DONE: `projects.detail`
- [x] DONE: `tasks.open`
- [x] DONE: `tasks.by_project`
- [x] DONE: `decisions.recent`
- [x] DONE: `violations.open`
- [x] DONE: `violations.by_file`
- [x] DONE: `notes.recent`
- [x] DONE: `code.symbols_by_file`
- [x] DONE: `code.callers`
- [x] DONE: `code.callees`
- [x] DONE: `evals.recent`

### Phase 4: Toolchain Command Support

- [x] DONE: Add `command_shell.py` with allowlisted argv execution.
- [x] DONE: Forbid `shell=True`.
- [x] DONE: Add output caps and timeouts.
- [x] DONE: Implement `toolchain python`.
- [x] DONE: Implement `toolchain go`.
- [x] DONE: Implement `toolchain security`.
- [x] DONE: Implement `lint fix` as the Python lint subset.

Initial allowlist:

- [x] DONE: `uv run ruff check src tests --fix`
- [x] DONE: `uv run mypy src`
- [x] DONE: `uv run pytest -q`
- [x] DONE: `semgrep scan`
- [x] DONE: `trivy fs .`
- [x] DONE: `gofumpt -w .`
- [x] DONE: `go fmt ./...`
- [x] DONE: `go test ./...`
- [x] DONE: `govulncheck ./...`

### Phase 5: Parser Staging and Watcher

- [x] DONE: Design parser staging storage: files, temp DB, or in-memory queue.
- [x] DONE: Add `command_parse_stage.py`.
- [x] DONE: Implement `code parse` against existing tree-sitter pipeline.
- [x] DONE: Implement `code stage` without graph DB ingest.
- [x] DONE: Implement `code commit-index` through existing ingest boundary.
- [x] DONE: Prototype `code watch` with watchdog.
- [x] DONE: Ensure watcher never pushes to graph DB without explicit commit.

### Phase 6: Embedding Commands

- [x] DONE: Add `command_embed.py`.
- [x] DONE: Implement `embed documents` using text embedding services.
- [x] DONE: Implement `embed code` using code embedding services.
- [x] DONE: Validate embedding dimensions before writes.
- [x] DONE: Reuse existing model/config paths.

### Phase 7: Agent Category Commands

- [x] DONE: Add CLI templates for `agent audit`.
- [x] DONE: Add CLI templates for `agent map`.
- [x] DONE: Add CLI templates for `agent fix`.
- [x] DONE: Add CLI templates for `agent validate`.
- [x] DONE: Add CLI templates for `agent document`.
- [x] DONE: Route through existing agent tools where available.
- [x] DONE: Return task IDs for long-running agent work.

### Phase 8: Workflow Command

- [x] DONE: Keep a compatibility path to current `run_subagent_workflow`.
- [ ] After Task 026, route `workflow start` through profile-selected workflow runtime.
- [ ] Support task type/profile selection.
- [ ] Support polling via existing background task status tools.

### Phase 9: Reference CLI Adapter

- [x] DONE: Decide whether this repo should include a reference adapter or only docs/snippets.
- [x] DONE: If included, add a tiny adapter that sends snippets to `execute`.
- [x] DONE: Keep oh-my-pi-specific configuration outside server internals unless requested.

## Acceptance Criteria

- No new command-specific MCP tools are added.
- `execute` can run a snippet that calls existing MCP tools.
- Curated command templates exist for every command in the catalog.
- DB normal path uses named templates, not raw Cypher.
- Raw Cypher is gated and documented as a debug escape hatch.
- Toolchain commands use strict argv allowlists.
- Parser watcher stages changes and does not write directly to graph DB.
- Embedding commands use existing embedding service/config paths.
- Agent category commands avoid tool search by routing to known current capabilities.
- `workflow start` is clearly blocked on Task 026 for final implementation.

## Test Plan

Focused unit tests:

```bash
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present \
MEM_GRAPH_LOGFIRE_ENABLED=false \
OTEL_SDK_DISABLED=true \
uv run pytest tests/commands -q
```

Parser/DB regression:

```bash
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present \
MEM_GRAPH_LOGFIRE_ENABLED=false \
OTEL_SDK_DISABLED=true \
uv run pytest tests/test_parsers.py tests/test_db.py -q
```

Broad gate:

```bash
uv run ruff check .
uv run mypy .
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true uv run pytest
make evals-ci
```

## Open Questions

1. Should DB templates be Python-defined, `.cypher` files, or both?
2. Should parser staging use a temp Ladybug DB or serialized parser batches?
3. Should `code watch` be a long-running CLI-side process or server-side background task?
4. Should shell execution happen through the server at all, or should some toolchain commands stay CLI-local?
5. Which exact oh-my-pi custom-tool schema should the reference templates target?
