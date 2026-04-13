# Deployment Documentation

## Purpose
This document explains how to run the Syntx Memory MCP Server locally and what to configure when promoting it to staging or production. It also covers the OpenTelemetry switches added for infrastructure-level observability.

## Runtime Requirements

- Python 3.14+
- Ollama reachable for embedding generation
- A writable Ladybug database path
- Port `9100` available unless `MCP_PORT` is overridden

## Local Development

### Installation

```bash
uv sync
```

If you are not using `uv`, an editable install still works:

```bash
pip install -e .
```

### Minimal `.env`

```bash
MCP_HOST=127.0.0.1
MCP_PORT=9100
MCP_TRANSPORT=http
LADYBUG_DB_PATH=./data/syntx_memory.lbug
OLLAMA_EMBED_DIM=768
MEM_GRAPH_WEBSITE=https://github.com/michael/syntx-memory
```

Version metadata is read from `pyproject.toml` and exposed through both the `get_server_info` MCP tool and `GET /info`.

### Start the Server

```bash
uv run main.py
```

The server will be available at `http://127.0.0.1:9100`.

Useful inspection endpoints:

```bash
curl http://127.0.0.1:9100/info
curl http://127.0.0.1:9100/health
```

## OpenTelemetry

OpenTelemetry is initialized from `src/mem_graph/observability/otel_setup.py` during server startup.

### Default Behavior

- Telemetry stays disabled when no exporter is configured.
- If you set `MEM_GRAPH_OTEL_ENABLED=true` without an OTLP endpoint, the server falls back to console span and metric export for local debugging.
- If you set `OTEL_EXPORTER_OTLP_ENDPOINT` (or the trace/metric endpoint variants), the server enables OTLP export automatically.

### Recommended Local Debugging Config

```bash
MEM_GRAPH_OTEL_ENABLED=true
MEM_GRAPH_OTEL_CONSOLE_EXPORTER=true
```

### Recommended OTLP Export Config

```bash
MEM_GRAPH_OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_SERVICE_NAME=syntx-memory
```

The implementation currently emits:

- Tool spans for the major agent-facing workflows and filesystem/memory/violation tools
- Orchestrator graph node spans and retry transitions
- Graph-query spans with query class, fingerprint, parameter count, duration, and row count
- Metrics for tool duration, background task throughput, and graph-query latency/result counts
- Structured log correlation through `trace_id` and `span_id`

### Redaction Rules

The telemetry path is intentionally conservative:

- Graph-query spans do not store raw query text or parameters.
- Tool spans capture names, duration, and coarse execution metadata rather than payload bodies.
- Exceptions may still surface error types for debugging, but not full input payloads by design.

## Testing and Evals

Run the full test suite:

```bash
uv run pytest
```

Run the baseline deterministic eval suites:

```bash
uv run mem-graph-evals --mode fixture
```

Run the live agent evals once provider credentials are configured:

```bash
uv run mem-graph-evals --mode live
```

## Staging and Production

### Systemd Example

```ini
[Unit]
Description=Syntx Memory MCP Server
After=network.target

[Service]
User=syntx
Group=syntx
WorkingDirectory=/opt/syntx-memory
Environment=PATH=/opt/syntx-memory/.venv/bin
ExecStart=/opt/syntx-memory/.venv/bin/uv run main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### Reverse Proxy Notes

If you front the server with Nginx or another proxy, forward `/mcp`, `/sse`, `/info`, `/health`, and any dashboard routes you expose to operators.

### Backups

Back up the Ladybug database file regularly before upgrades or schema changes.

## Troubleshooting

### Server Fails to Start

- Verify Ollama is reachable: `ollama list`
- Confirm the database directory is writable
- Check logs for startup failures: `journalctl -u syntx-memory`

### No Telemetry Appears

- Confirm `MEM_GRAPH_OTEL_ENABLED=true` or an OTLP endpoint is set
- For local debugging, enable `MEM_GRAPH_OTEL_CONSOLE_EXPORTER=true`
- Check whether `OTEL_SDK_DISABLED=true` is set anywhere in the environment

### No Eval Output Appears

- Use `--mode fixture` first to verify the framework without model calls
- Use `--json` if you want the full report payload instead of the text summary

## References to Code

- `main.py`
- `src/mem_graph/server.py`
- `src/mem_graph/db.py`
- `src/mem_graph/observability/otel_setup.py`
- `src/mem_graph/evals/evaluator.py`
