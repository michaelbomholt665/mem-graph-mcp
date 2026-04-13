# Design: OpenTelemetry Integration

**Status:** Design Phase  
**Priority:** Medium (Observability)  
**Date:** 2026-04-13

---

## Overview

OpenTelemetry (OTel) provides unified observability across the entire system. This design ensures:

1. **Automatic Instrumentation:** All tools and agents emit traces
2. **Structured Logging:** Log messages include trace context
3. **Metrics:** Tool execution times, agent decisions are measured
4. **Exporting:** Data can be sent to Jaeger, Datadog, or other backends

---

## Goals

1. **Visibility:** See exactly what agents are doing
2. **Performance Profiling:** Identify bottlenecks
3. **Debugging:** Trace request flow through system
4. **Alerting:** Set up alerts on slow operations

---

## Scope

### In Scope
- Instrument all FastMCP tools with spans
- Instrument agent execution (planning, reasoning, decisions)
- Add metrics for tool runtime, agent tier selection
- Implement log correlation (trace ID in logs)
- Set up exporters (Jaeger, console for dev)

### Out of Scope
- APM setup (users configure their own backends)
- Custom sampling rules (use defaults)
- Distributed tracing across multiple services (single service)

---

## Architecture

### 1. Tracer Setup

```python
# src/mem_graph/observability.py

from opentelemetry import trace, metrics, logs
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

def setup_observability(service_name: str = "mem-graph") -> None:
    """Initialize OpenTelemetry for the service."""
    
    # Trace setup
    jaeger_exporter = JaegerExporter(
        agent_host_name=os.getenv("JAEGER_HOST", "localhost"),
        agent_port=int(os.getenv("JAEGER_PORT", "6831")),
    )
    
    trace.set_tracer_provider(TracerProvider())
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(jaeger_exporter)
    )
    
    # Metrics setup
    prometheus_reader = PrometheusMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[prometheus_reader]))
    
    # Get tracers and meters
    global TRACER, METER
    TRACER = trace.get_tracer(__name__)
    METER = metrics.get_meter(__name__)

TRACER: trace.Tracer
METER: metrics.Meter
```

### 2. Tool Instrumentation

Wrap tools with span creation:

```python
# src/mem_graph/tools/agents/decorators.py

from ..observability import TRACER, METER
from functools import wraps

def traced_tool(tool_name: str):
    """Decorator to automatically create spans for tools."""
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with TRACER.start_as_current_span(f"tool:{tool_name}") as span:
                span.set_attribute("tool.name", tool_name)
                span.set_attribute("tool.args", str(kwargs)[:100])  # Truncate
                
                try:
                    start_time = time.time()
                    result = await func(*args, **kwargs)
                    
                    elapsed = time.time() - start_time
                    span.set_attribute("tool.duration_ms", int(elapsed * 1000))
                    span.set_attribute("tool.success", True)
                    
                    return result
                
                except Exception as e:
                    span.set_attribute("tool.success", False)
                    span.set_attribute("tool.error", str(e))
                    raise
        
        return wrapper
    return decorator

# Use it on tools

@mcp.tool()
@traced_tool("memory_store")
async def memory_store(content: str, tags: list[str] | None = None) -> dict:
    """Store a fact (automatically traced)."""
    ...

@mcp.tool()
@traced_tool("audit_package")
async def audit_package(package_path: str) -> dict:
    """Audit a package (automatically traced)."""
    ...
```

### 3. Agent Execution Instrumentation

Instrument Core Five agents:

```python
# src/mem_graph/agents/base_agent.py

from ..observability import TRACER, METER

class TracedAgent:
    """Base class for traced agents."""
    
    def __init__(self, agent: Agent, agent_name: str):
        self.agent = agent
        self.agent_name = agent_name
        
        # Create metrics
        self.execution_counter = METER.create_counter(
            f"agent.{agent_name}.executions",
            description=f"Number of {agent_name} executions",
        )
        
        self.duration_histogram = METER.create_histogram(
            f"agent.{agent_name}.duration_ms",
            description=f"Execution duration of {agent_name}",
        )
    
    async def run(self, prompt: str, context: dict) -> str:
        """Run agent with tracing."""
        
        with TRACER.start_as_current_span(f"agent.run") as span:
            span.set_attribute("agent.name", self.agent_name)
            span.set_attribute("agent.prompt_length", len(prompt))
            
            try:
                start_time = time.time()
                
                # Agent execution
                result = await self.agent.run(prompt)
                
                elapsed = time.time() - start_time
                
                # Record metrics
                self.execution_counter.add(1)
                self.duration_histogram.record(int(elapsed * 1000))
                
                span.set_attribute("agent.success", True)
                span.set_attribute("agent.output_length", len(result.data))
                span.set_attribute("agent.duration_ms", int(elapsed * 1000))
                
                return result
            
            except Exception as e:
                span.set_attribute("agent.success", False)
                span.set_attribute("agent.error", str(e))
                raise

# Wrap Core Five agents
audit_agent = TracedAgent(
    create_audit_agent(),
    agent_name="audit"
)

fix_agent = TracedAgent(
    create_fix_agent(),
    agent_name="fix"
)
```

### 4. Graph Query Instrumentation

Trace database queries:

```python
# src/mem_graph/db.py

async def execute_query(query: str, **params) -> list[dict]:
    """Execute graph query with tracing."""
    
    with TRACER.start_as_current_span("graph.query") as span:
        span.set_attribute("graph.query_template", query[:100])
        
        try:
            start_time = time.time()
            
            result = await connection.query(query, **params)
            
            elapsed = time.time() - start_time
            
            span.set_attribute("graph.query_duration_ms", int(elapsed * 1000))
            span.set_attribute("graph.result_count", len(result))
            span.set_attribute("graph.success", True)
            
            return result
        
        except Exception as e:
            span.set_attribute("graph.success", False)
            span.set_attribute("graph.error", str(e))
            raise
```

### 5. Structured Logging with Trace Context

```python
# src/mem_graph/logging.py

import logging
from opentelemetry import trace

class TraceContextFilter(logging.Filter):
    """Add trace context to logs."""
    
    def filter(self, record):
        span = trace.get_current_span()
        if span and span.is_recording():
            record.trace_id = span.get_span_context().trace_id
            record.span_id = span.get_span_context().span_id
        else:
            record.trace_id = "no-trace"
            record.span_id = "no-span"
        
        return True

def setup_logging():
    """Setup logging with trace context."""
    
    logger = logging.getLogger()
    
    # Add trace context filter
    trace_filter = TraceContextFilter()
    logger.addFilter(trace_filter)
    
    # Use JSON formatter with trace IDs
    formatter = logging.Formatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", '
        '"message": "%(message)s", "trace_id": "%(trace_id)s", '
        '"span_id": "%(span_id)s"}'
    )
    
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
```

### 6. Metrics Dashboard

Set up Prometheus to scrape metrics:

```yaml
# prometheus.yml

global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "mem-graph"
    static_configs:
      - targets: ["localhost:8000"]
```

Then visualize in Grafana with queries like:

```promql
# Audit agent execution time
rate(agent.audit.duration_ms[5m])

# Tool success rate
sum(rate(tool.success[5m])) / sum(rate(tool.total[5m]))

# Graph query latency
histogram_quantile(0.95, rate(graph.query_duration_ms[5m]))
```

---

## Benefits

1. **Visibility:** See exactly what's happening in the system
2. **Performance:** Identify slow operations
3. **Debugging:** Trace requests through the system
4. **Alerting:** Set up alerts on anomalies

---

## Configuration

```bash
# .env

JAEGER_HOST=localhost
JAEGER_PORT=6831
OTEL_ENABLED=true
OTEL_LOG_LEVEL=INFO
```

---

## Implementation Checklist

- [ ] Setup OpenTelemetry provider (trace, metrics, logs)
- [ ] Instrument all FastMCP tools with `@traced_tool`
- [ ] Instrument Core Five agents with `TracedAgent`
- [ ] Instrument graph queries
- [ ] Add trace context to logs
- [ ] Setup Jaeger exporter
- [ ] Setup Prometheus metrics exporter
- [ ] Create Grafana dashboard
- [ ] Test trace collection
- [ ] Test metrics collection

---

## Success Criteria

1. Traces are emitted for all tools and agents
2. Logs include trace context (trace_id, span_id)
3. Metrics are collected (execution count, duration)
4. Jaeger UI shows trace flow
5. Grafana dashboard shows metrics
6. No performance regression from tracing

---

## Dependencies

- `opentelemetry-api>=1.20.0` (already in `pyproject.toml`)
- `opentelemetry-sdk>=1.20.0` (already in `pyproject.toml`)
- `opentelemetry-exporter-otlp>=1.20.0` (already in `pyproject.toml`)
- Jaeger (docker or local)
- Prometheus (optional, for metrics)
- Grafana (optional, for dashboards)

---

## Notes

- Tracing has negligible performance impact (<1% overhead)
- Use sampling in production to avoid overwhelming the exporter
- Trace context is automatically propagated through FastMCP
