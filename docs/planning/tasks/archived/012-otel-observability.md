# OpenTelemetry Observability Tasklist

## Goal

Instrument the server, tool layer, graph access, and orchestration path with OpenTelemetry so traces, metrics, and correlated logs are available without changing business behavior.

Prerequisite: See `docs/planning/tasks/007-fastmcp-task.md` — OTel can be enabled before or after 007; if you depend on FastMCP-specific spans, complete 007 first.

## Dependencies

- Reuse the current logging entry points instead of introducing a parallel logging stack.
- Coordinate with the Logfire plan so OpenTelemetry handles infrastructure-grade telemetry and Logfire handles agent-level live visibility.
- Follow `docs/planning/design/012-otel.md` and the target structure in `docs/planning/design/FILE_STRUCTURE.md`.

## Work Envelope

- Planned new files: 4
- Planned file edits: 10-11
- Shape: edit-heavy, single task
- Why this size works: the infrastructure is mostly new modules plus broad but still bounded instrumentation edits across existing entry points

## Planned Files

New files:
- `src/mem_graph/observability/__init__.py`
- `src/mem_graph/observability/otel_setup.py`
- `src/mem_graph/observability/instrumentation.py`
- `src/mem_graph/observability/metrics.py`

Existing files to edit:
- `src/mem_graph/server.py`
- `src/mem_graph/logging.py`
- `src/mem_graph/db.py`
- `src/mem_graph/agents/orchestrator_graph.py`
- `src/mem_graph/tools/agents/audit.py`
- `src/mem_graph/tools/agents/map.py`
- `src/mem_graph/tools/agents/triage.py`
- `src/mem_graph/tools/memory/memory.py`
- `src/mem_graph/tools/filesystem/filesystem.py`
- `src/mem_graph/tools/work/violations.py`
- `docs/documentation/deployment.md`

## Tasklist

- [x] Create an OpenTelemetry setup module that configures tracer, meter, exporter, and environment-driven enablement in one place.
- [x] Add shared instrumentation helpers or decorators so tool tracing is consistent instead of hand-coded per module.
- [x] Instrument graph queries with span metadata for query class, duration, and result count without logging full sensitive payloads.
- [x] Add tool-level spans and runtime metrics to the agent-facing tool modules that drive the heaviest workflows.
- [x] Instrument orchestrator graph transitions so node boundaries and retries appear in trace timelines.
- [x] Update the logging layer to attach trace and span context to structured log output.
- [x] Mount OpenTelemetry bootstrap into server startup with a safe disabled path for local environments that do not export telemetry.
- [x] Define baseline counters and histograms for tool duration, task throughput, and graph-query latency.
- [x] Document exporter configuration, local development defaults, and what should be redacted.
- [x] Validate that instrumentation does not materially change tool contracts or force new runtime dependencies into every call path.

## Out Of Scope

- Distributed tracing across multiple services
- Custom sampling strategies beyond sensible defaults
- Replacing Logfire or Python logging with a new observability product

## Done When

- [x] Traces exist for core tools, orchestrator graph runs, and graph queries.
- [x] Logs can be correlated with active traces.
- [x] Basic metrics are exposed for latency and throughput.
- [x] Telemetry can be disabled cleanly in environments that do not provide exporters.

## References

- `docs/planning/design/012-otel.md`
- `docs/planning/design/015-logfire.md`
- `docs/planning/design/FILE_STRUCTURE.md`
- `docs/planning/design/links.md`
