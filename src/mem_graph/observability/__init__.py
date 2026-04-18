"""Shared observability helpers for tracing and metrics."""

from __future__ import annotations

from .instrumentation import traced_span, traced_tool
from .logfire_setup import (
    LogfireState,
    logfire_debug,
    logfire_enabled,
    logfire_exception,
    logfire_info,
    setup_logfire,
    shutdown_logfire,
)
from .metrics import record_graph_query, record_task_event, record_tool_result
from .otel_setup import ObservabilityState, setup_observability, shutdown_observability

__all__ = [
    "LogfireState",
    "ObservabilityState",
    "logfire_debug",
    "logfire_enabled",
    "logfire_exception",
    "logfire_info",
    "record_graph_query",
    "record_task_event",
    "record_tool_result",
    "setup_logfire",
    "setup_observability",
    "shutdown_logfire",
    "shutdown_observability",
    "traced_span",
    "traced_tool",
]
