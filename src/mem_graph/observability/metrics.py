"""OpenTelemetry metrics helpers for mem-graph."""

from __future__ import annotations

from opentelemetry import metrics

AttributeValue = str | bool | int | float
Attributes = dict[str, AttributeValue]

_METER = metrics.get_meter("mem_graph.observability")

_TOOL_CALL_COUNTER = _METER.create_counter(
    "mem_graph.tool.calls",
    unit="1",
    description="Count of tool executions grouped by tool name and outcome.",
)
_TOOL_DURATION_HISTOGRAM = _METER.create_histogram(
    "mem_graph.tool.duration.ms",
    unit="ms",
    description="Execution latency for tool workflows.",
)
_TASK_EVENT_COUNTER = _METER.create_counter(
    "mem_graph.task.events",
    unit="1",
    description="Background task lifecycle events grouped by tool and status.",
)
_GRAPH_QUERY_COUNTER = _METER.create_counter(
    "mem_graph.graph.query.calls",
    unit="1",
    description="Graph query executions grouped by query class and outcome.",
)
_GRAPH_QUERY_DURATION_HISTOGRAM = _METER.create_histogram(
    "mem_graph.graph.query.duration.ms",
    unit="ms",
    description="Graph query latency in milliseconds.",
)
_GRAPH_QUERY_RESULT_HISTOGRAM = _METER.create_histogram(
    "mem_graph.graph.query.result_count",
    unit="1",
    description="Number of rows returned by graph queries.",
)


def _sanitize_attributes(attributes: dict[str, object] | None) -> Attributes:
    clean: Attributes = {}
    if not attributes:
        return clean

    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            clean[key] = value
            continue
        clean[key] = str(value)

    return clean


def record_tool_result(
    tool_name: str,
    duration_ms: float,
    *,
    status: str,
    component: str = "tool",
) -> None:
    """Record latency and outcome metrics for a tool workflow."""
    attributes = _sanitize_attributes(
        {
            "tool.name": tool_name,
            "tool.status": status,
            "mem_graph.component": component,
        }
    )
    _TOOL_CALL_COUNTER.add(1, attributes)
    _TOOL_DURATION_HISTOGRAM.record(duration_ms, attributes)


def record_task_event(tool_name: str, *, status: str, source: str = "queue") -> None:
    """Record a background task lifecycle transition."""
    attributes = _sanitize_attributes(
        {
            "tool.name": tool_name,
            "task.status": status,
            "task.source": source,
        }
    )
    _TASK_EVENT_COUNTER.add(1, attributes)


def record_graph_query(
    query_class: str,
    duration_ms: float,
    *,
    status: str,
    result_count: int | None = None,
) -> None:
    """Record graph query metrics without exposing query payloads."""
    attributes = _sanitize_attributes(
        {
            "graph.query.class": query_class,
            "graph.status": status,
        }
    )
    _GRAPH_QUERY_COUNTER.add(1, attributes)
    _GRAPH_QUERY_DURATION_HISTOGRAM.record(duration_ms, attributes)

    if result_count is not None:
        _GRAPH_QUERY_RESULT_HISTOGRAM.record(result_count, attributes)