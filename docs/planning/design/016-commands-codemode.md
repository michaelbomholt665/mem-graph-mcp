# Design: Curated CLI Commands Through CodeMode Execute

**Status:** Design Phase  
**Priority:** High  
**Date:** 2026-04-19  

## Summary

Add a curated command layer for local/custom CLIs without adding more MCP tools.

The command path is:

```text
oh-my-pi/custom CLI command
  -> running mem-graph MCP server
  -> existing CodeMode `execute`
  -> small generated Python snippet
  -> existing MCP tools or importable server support helpers
```

The purpose is to reduce tool searches. The CLI should expose stable, named commands for common operations instead of making the agent search the MCP catalog and build tool-call plans every time.

## Design Rule

Do not add one MCP tool per command.

Commands are CLI-owned templates that call the existing CodeMode execution tool. Server changes should be limited to:

- wiring FastMCP CodeMode if it is not currently active;
- adding importable support modules for gaps that existing tools do not cover;
- adding policy gates for shell, raw Cypher, and Python execution.

## Command Groups

### Toolchain Commands

| Command | Description |
|---|---|
| `toolchain go` | Run Go formatting, tests, vulnerability checks, and optional filesystem/container security scans. |
| `toolchain python` | Run Ruff fix/check, mypy, pytest, Semgrep, and optional Trivy filesystem scan. |
| `toolchain security` | Run cross-language security checks: Semgrep, Trivy fs, govulncheck when Go is present, and dependency vulnerability scanners where configured. |

Initial command mappings:

```text
toolchain go:
  gofumpt -w .
  go fmt ./...
  go test ./...
  govulncheck ./...
  trivy fs .

toolchain python:
  uv run ruff check src tests --fix
  uv run mypy src
  uv run pytest -q
  semgrep scan
  trivy fs .

toolchain security:
  semgrep scan
  trivy fs .
  govulncheck ./...          # only when Go module is detected
```

These should use a strict allowlisted command runner. The CLI may render a CodeMode snippet that imports a support helper such as `mem_graph.services.command_shell.run_allowed_command(...)`.

### Agent Category Commands

One command per agent category. These should map to existing agent capabilities and later to the workflow resource system from Task 026.

| Command | Description |
|---|---|
| `agent audit` | Start audit-oriented analysis for code quality, policy, safety, and security findings. |
| `agent map` | Start codebase mapping for structure, feature relationships, dependencies, and entry points. |
| `agent fix` | Start targeted remediation or implementation work for a scoped issue. |
| `agent validate` | Start validation for tests, regressions, changed behavior, and acceptance checks. |
| `agent document` | Start documentation, decision capture, notes, task summary, and memory-bank update work. |

Implementation preference:

- Use existing MCP tools through CodeMode `call_tool(...)` where possible.
- Activate the needed lazy namespace inside the snippet.
- Return a task ID when the underlying operation is long-running.

### Workflow Command

| Command | Description |
|---|---|
| `workflow start` | Start the orchestrator or multi-agent workflow selected by task type/profile. |

Dependency:

- This command should be fully implemented after `docs/planning/tasks/026-agent-workflows.md`.
- Until Task 026 lands, it may call the current `run_subagent_workflow` compatibility entry point.

### Code Parsing Commands

| Command | Description |
|---|---|
| `code parse` | Parse a file or codebase with tree-sitter and produce code-symbol/index artifacts. |
| `code watch` | Start a watchdog-based file watcher that stages parser updates as files change. |
| `code stage` | Stage parser output without writing it to the graph DB. |
| `code commit-index` | Commit staged parser/index output into the graph DB after a task is complete. |

Important design point:

Parser automation should not push every file-save directly into the graph DB. Add a staging layer so watcher output can be reviewed, batched, and committed when a task is done.

Suggested staging model:

```text
source file change
  -> tree-sitter parse
  -> staging area on disk or temp DB
  -> task completion / explicit command
  -> graph DB ingest
```

This aligns with the existing parser architecture:

- extraction and resolution stay outside persistence;
- `app/parsers/persist.py` builds batches;
- `app/parsers/ingest.py` remains the Ladybug execution boundary.

### Embedding Commands

| Command | Description |
|---|---|
| `embed documents` | Send documents, notes, docs pages, or selected text files to the text embedder. |
| `embed code` | Send code files or code symbols to the code embedder. |

These commands should call importable embedding services, not raw model clients. They should respect configured model names and dimensions.

### DB Commands

| Command | Description |
|---|---|
| `db migrate` | Initialize or migrate the Ladybug DB with idempotent schema/bootstrap checks. |
| `db inspect` | Run predefined graph inspection templates for common debugging views. |
| `db query-template` | Execute a named Cypher template with typed parameters. |
| `db cypher` | Run raw Cypher only as a gated debugging escape hatch. |

Raw Cypher should not be the normal interface. Once the DB schema settles, common graph reads should be named templates.

Template examples:

```text
projects.list
projects.detail
tasks.open
tasks.by_project
decisions.recent
violations.open
violations.by_file
notes.recent
memory.search_summary
code.files_changed
code.symbols_by_file
code.callers
code.callees
evals.recent
schema.indexes
schema.counts
```

Suggested support module:

```text
src/mem_graph/services/command_db.py
```

Responsibilities:

- hold named query templates;
- validate template names and typed params;
- enforce read-only mode by default;
- provide a gated raw Cypher debug path.

### Eval and Diagnostic Commands

| Command | Description |
|---|---|
| `eval gate` | Run fixture, CI, live, or release eval suites. |
| `lint fix` | Run Ruff fix/check and mypy for the Python project. |
| `python repl` | Execute a short Python diagnostic snippet through CodeMode `execute`. |
| `shell execute` | Run a strictly allowlisted shell command such as `git`, `uv`, `make`, or scanners. |

These are high-trust local commands. They should require explicit CLI approval or environment gates when mutating or executing arbitrary code.

## Command Catalog

Short canonical list:

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

## CodeMode Snippet Pattern

Generated snippets should return a stable result envelope:

```python
def ok(command, data=None, warnings=None):
    return {
        "ok": True,
        "command": command,
        "status": "completed",
        "data": data or {},
        "warnings": warnings or [],
        "error": None,
    }
```

Example: parse codebase through existing parser tools:

```python
await call_tool("tools_activate", {"namespace": "code"})
indexed = await call_tool("index_code_tree", {
    "root": "/home/michael/projects/python/memory/src",
    "include": ["**/*.py"],
    "exclude": ["**/__pycache__/**"],
    "max_files": 200,
})
return ok("code.parse", {"indexed": indexed})
```

Example: start an agent category:

```python
await call_tool("tools_activate", {"namespace": "audit"})
task = await call_tool("orchestrate_codebase", {
    "package_path": "/home/michael/projects/python/memory/src/mem_graph",
    "project_id": "mem-graph",
    "subagent_name": "map",
    "batch_size": 5,
    "file_extension": ".py",
})
return ok("agent.map", {"task": task})
```

## Support Modules

Add support modules only when an operation cannot be cleanly expressed through existing MCP tools:

```text
src/mem_graph/services/command_db.py
src/mem_graph/services/command_shell.py
src/mem_graph/services/command_evals.py
src/mem_graph/services/command_parse_stage.py
src/mem_graph/services/command_embed.py
```

These are normal Python service modules, not MCP tools.

## Safety

- `db cypher`, `python repl`, and `shell execute` are escape hatches, not default paths.
- Prefer DB templates over raw Cypher.
- Prefer toolchain presets over raw shell.
- Prefer parser staging over automatic DB writes.
- Never use `shell=True`.
- Cap output and execution time.
- Do not log raw prompts, secrets, raw Cypher params, or full Python snippets.
- Keep execution local/authenticated.

## Implementation Phases

1. Wire/verify CodeMode `execute`.
2. Define CLI command templates and result envelope.
3. Implement DB templates and read-only query support.
4. Implement toolchain allowlisted runner.
5. Implement parser staging and watcher.
6. Implement embed document/code command helpers.
7. Connect agent category commands to current agents.
8. Connect `workflow start` after Task 026 is implemented.

## Open Questions

1. Should `code watch` stage into files, a temp Ladybug DB, or an in-memory queue?
2. Should `toolchain go` detect Go projects automatically or fail unless `go.mod` exists?
3. Should `db inspect` templates be Python-defined or loaded from `.cypher` files?
4. Should `python repl` be exposed in normal CLI help or hidden under a debug group?
