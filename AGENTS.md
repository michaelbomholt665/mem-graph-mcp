# AGENTS.md

## Project Overview

Mem-graph Memory is a Python 3.14 FastMCP server that stores agent memory in a Ladybug graph database. It captures and links conversations, projects, tasks, decisions, notes, violations, Jina issues, code symbols, and eval runs, with semantic search powered by local embedding models.

Core technologies:
- Python 3.14 with `src/` package layout.
- FastMCP for MCP tools, HTTP routes, and server lifecycle.
- Ladybug DB for graph persistence; schema lives in `schema/agent_memory_schema.cypher`.
- Pydantic AI, pydantic-graph, and pydantic-evals for agent workflows and evals.
- Tree-sitter parser pipeline for code symbol extraction and graph indexing.
- Logfire and OpenTelemetry for optional observability.
- `uv` for dependency and command execution.

Important directories:
- `src/mem_graph/server.py`: FastMCP server bootstrap and HTTP app wiring.
- `src/mem_graph/app/`: web routes, lifespan, middleware, parser pipeline, and app-level helpers.
- `src/mem_graph/tools/`: MCP tool implementations grouped by namespace.
- `src/mem_graph/services/`: reusable service layer for search, embeddings, Jina, reporting, and tasks.
- `src/mem_graph/agents/`: Pydantic AI agent bundles and workflow orchestration.
- `src/mem_graph/evals/`: deterministic and live eval framework.
- `tests/`: pytest suite and fixtures.
- `docs/documentation/`: project documentation.

## Setup Commands

Use Python 3.14. The repository has `.python-version` set to `3.14`.

Install dependencies:

```bash
uv sync --dev
```

If the virtualenv already exists, direct commands under `.venv/bin/` are also fine:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Copy environment defaults before running the server:

```bash
cp .env.example .env
```

Key environment variables:
- `LADYBUG_DB_PATH`: database file path, default `./data/syntx_memory.lbug`.
- `MCP_TRANSPORT`: `streamable-http`, `http`, `stdio`, or `sse`.
- `MCP_HOST` / `MCP_PORT`: default local HTTP endpoint is `127.0.0.1:9100`.
- `OLLAMA_EMBED_DIM`: must match the DB schema embedding dimension for the selected models.
- `OLLAMA_CODE_EMBED_MODEL` / `OLLAMA_TEXT_EMBED_MODEL`: embedding model names.
- `MEM_GRAPH_LOGFIRE_ENABLED`, `MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE`, and `OTEL_SDK_DISABLED`: control telemetry in tests and local runs.

## Development Workflow

Start the MCP server:

```bash
make run
```

Equivalent direct command:

```bash
uv run main.py
```

Open the FastMCP Inspector against the streamable HTTP endpoint:

```bash
make inspect
```

The inspector expects:

```text
http://localhost:9100/mcp
```

Run the server with telemetry disabled for local debugging when network access is unavailable:

```bash
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true uv run main.py
```

Do not hard-code the package version. `pyproject.toml` is the source of truth and `mem_graph.__version__` exports it at runtime.

## Testing Instructions

Pytest is configured by `pytest.ini`:
- `pythonpath = src`
- `asyncio_mode = auto`
- tests live under `tests/`
- custom marker: `evals`

Run the full suite:

```bash
uv run pytest -q
```

In network-restricted agent environments, disable telemetry export to avoid Logfire/OTLP network retries:

```bash
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present \
MEM_GRAPH_LOGFIRE_ENABLED=false \
OTEL_SDK_DISABLED=true \
uv run pytest -q
```

If using the existing virtualenv:

```bash
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present \
MEM_GRAPH_LOGFIRE_ENABLED=false \
OTEL_SDK_DISABLED=true \
.venv/bin/pytest -q
```

Run a focused test file:

```bash
uv run pytest tests/test_parsers.py -q
```

Run a single test:

```bash
uv run pytest tests/test_tools.py::test_memory_store_and_list -q
```

Run lint and type checks:

```bash
uv run ruff check src tests
uv run mypy src
```

Run parser and DB regression tests after changing parser, schema, ingest, or Ladybug code:

```bash
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present \
MEM_GRAPH_LOGFIRE_ENABLED=false \
OTEL_SDK_DISABLED=true \
uv run pytest tests/test_parsers.py tests/test_db.py -q
```

Tests use fresh temporary Ladybug databases and deterministic embedding shims. Most tests should not require Ollama or network access.

## Eval Commands

Run deterministic fixture evals:

```bash
make evals
```

Run the fast pre-merge eval gate:

```bash
make evals-ci
```

Run live evals only when model credentials and providers are configured:

```bash
make evals-live
make evals-release
```

Direct eval entry point:

```bash
uv run mem-graph-evals --mode fixture --runs 1
uv run mem-graph-evals --mode fixture --output build/evals/fixture-report.json
```

Prefer fixture-backed evals for automated gates. Live evals are useful for manual debugging and release confidence, but can vary with model output.

## Code Style

General conventions:
- Keep the `src/` layout and import from `mem_graph.*`.
- Prefer existing tool, service, and model patterns over new abstractions.
- Return structured dictionaries from MCP tools unless the surrounding module uses typed Pydantic outputs.
- Keep user-facing HTTP and tool response shapes stable.
- Avoid hard-coded versions, database paths, model names, and API keys.

Formatting and static checks:
- Use Ruff for linting: `uv run ruff check src tests`.
- Use mypy for type checks: `uv run mypy src`.
- Use standard Python typing and Pydantic models where the codebase already does.
- Keep comments concise and only where they explain non-obvious behavior.

Async guidance:
- Many tools are async because FastMCP calls them that way.
- Avoid `anyio.to_thread.run_sync` for small local file operations in this repository; it has caused hangs under Python 3.14 in sandboxed test runs.
- Synchronous local file reads are acceptable in small bounded helpers already called from async tool wrappers.

## Architecture Notes

DB and schema:
- `src/mem_graph/db.py` owns Ladybug bootstrap, connection proxying, schema loading, vector and FTS index creation, and schema metadata validation.
- `schema/agent_memory_schema.cypher` defines node tables, relationship tables, vector indexes, and FTS indexes.
- Schema embedding column dimensions are substituted at bootstrap from `OLLAMA_EMBED_DIM`; keep tests compatible with the test fixture dimension.

Parser pipeline:
- Public parser tools live in `src/mem_graph/tools/code/parser.py`.
- Orchestration lives in `src/mem_graph/app/parsers/pipeline.py`.
- Extraction and resolution are separate from persistence.
- `src/mem_graph/app/parsers/persist.py` builds Cypher batches only.
- `src/mem_graph/app/parsers/ingest.py` is the Ladybug execution boundary for parser writes.
- Be careful with Ladybug FTS and vector indexes. Indexed columns often need drop/write/recreate handling.
- Parser relationship writes intentionally avoid native relationship `MERGE` because it can fail in Ladybug on some relationship batches.

Tool namespaces:
- Tools are grouped under namespaces such as `memory`, `work`, `notes`, `audit`, `filesystem`, `background`, `graph`, `integrations`, and `code`.
- Some namespaces are lazily activated. Use `tools_search` and `tools_activate` patterns when adding or testing tool discovery.

Observability:
- Logfire setup is in `src/mem_graph/observability/logfire_setup.py`.
- OpenTelemetry setup is in `src/mem_graph/observability/otel_setup.py`.
- The graph query wrapper records query class, fingerprint, parameter count, duration, and row counts. Do not add raw Cypher text or raw parameters to spans.

## Build and Deployment

There is no separate compiled build step for the Python package. Validate deployable state with:

```bash
uv run ruff check src tests
uv run mypy src
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true uv run pytest -q
make evals-ci
```

Runtime deployment needs:
- A writable Ladybug database path.
- Matching `OLLAMA_EMBED_DIM` and schema metadata.
- Running Ollama when live embedding generation is needed.
- Optional bearer token auth via `MEM_GRAPH_API_KEYS`.
- Optional Logfire/OTLP credentials if telemetry export is enabled.

## Security and Safety

- Never commit `.env`, API keys, bearer tokens, Logfire tokens, or database files.
- Prefer test DBs under temporary directories for automated tests.
- Use parameterized Ladybug queries for user-provided values.
- Validate dynamic labels, relationship names, table names, and index names with strict identifier regexes before interpolation.
- Do not log raw prompts, raw tool payloads, secrets, or full query parameters.
- `.github/hooks/` contains Copilot-oriented guardrails for tool safety, secrets scanning, governance auditing, import-graph changes, and session logging. Keep generated logs out of commits unless explicitly requested.

## Pull Request Guidelines

Before handing off changes, run the narrowest relevant tests first, then the broad gate when practical:

```bash
uv run ruff check src tests
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true uv run pytest -q
make evals-ci
```

For parser, DB, or schema work, always include:

```bash
uv run pytest tests/test_parsers.py tests/test_db.py -q
```

For dashboard/server metadata work, include:

```bash
uv run pytest tests/test_graph.py tests/test_server_metadata.py -q
```

For Jina integration work, include:

```bash
uv run pytest tests/test_jina.py tests/test_jina_embedder.py -q
```

Keep PR summaries factual:
- What changed.
- Why it changed.
- Which tests and evals were run.
- Any known limitations or intentionally skipped checks.

## Common Troubleshooting

Ladybug embedding dimension mismatch:
- Error shape: `Expected: 2048, Actual: 768` or similar.
- Confirm `OLLAMA_EMBED_DIM`, schema bootstrap substitution, and test embedding shim dimensions match.
- Use a fresh test DB after changing dimensions.

Logfire network warnings in tests:
- Disable telemetry export in local or sandboxed test runs:

```bash
MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE=if-token-present MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true uv run pytest -q
```

Parser ingest crashes or native Ladybug failures:
- Check FTS/vector index handling before mutating indexed columns.
- Keep parser DB execution inside `ingest.py`.
- Run `tests/test_parsers.py` in isolation before the full suite.

Ollama startup failures:
- Most tests mock embeddings and do not need Ollama.
- Live server runs and live evals need Ollama reachable at `OLLAMA_HOST`.
- `db_init_engine()` probes Ollama unless tests patch the probe.

Slow or hanging filesystem tests:
- Avoid thread-pool wrappers for small local file discovery/read operations.
- Prefer bounded synchronous filesystem calls inside already-async tool handlers.
