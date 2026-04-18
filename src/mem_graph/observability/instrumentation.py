"""Reusable tracing helpers for tools and orchestration flows."""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from functools import wraps
from inspect import iscoroutinefunction
from time import perf_counter
from typing import Any, Callable

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from .logfire_setup import logfire_exception, logfire_info
from .metrics import record_tool_result

AttributeValue = str | bool | int | float

_ERROR_TYPE_ATTR = "error.type"
_TOOL_DURATION_ATTR = "tool.duration_ms"
_TOOL_SUCCESS_ATTR = "tool.success"
_TOOL_ARGUMENT_COUNT_ATTR = "tool.argument_count"
_TOOL_BACKGROUND_TASK_ATTR = "tool.background_task"

_TRACER = trace.get_tracer("mem_graph.instrumentation")


def _set_attributes(span: Span, attributes: Mapping[str, object] | None) -> None:
    if not attributes:
        return

    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            span.set_attribute(key, value)
        else:
            span.set_attribute(key, str(value))


def _tool_attributes(
    tool_name: str,
    component: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, AttributeValue]:
    ctx = kwargs.get("ctx")
    return {
        "tool.name": tool_name,
        "mem_graph.component": component,
        _TOOL_ARGUMENT_COUNT_ATTR: len(args) + len(kwargs),
        _TOOL_BACKGROUND_TASK_ATTR: bool(getattr(ctx, "is_background_task", False)),
    }


@contextmanager
def traced_span(
    span_name: str,
    *,
    attributes: Mapping[str, object] | None = None,
) -> Generator[Span, None, None]:
    """Create a traced span with consistent error handling."""
    with _TRACER.start_as_current_span(span_name) as span:
        _set_attributes(span, attributes)
        try:
            yield span
        except Exception as exc:
            logfire_exception(
                "Span failed",
                span_name=span_name,
                error_type=type(exc).__name__,
            )
            span.set_attribute(_ERROR_TYPE_ATTR, type(exc).__name__)
            span.set_status(Status(StatusCode.ERROR))
            span.record_exception(exc)
            raise


def traced_tool(
    tool_name: str,
    *,
    component: str = "tool",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a sync or async tool entry point with tracing and metrics."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = perf_counter()
                attributes = _tool_attributes(tool_name, component, args, kwargs)
                logfire_info(
                    "Tool started",
                    tool_name=tool_name,
                    component=component,
                    argument_count=attributes[_TOOL_ARGUMENT_COUNT_ATTR],
                    background_task=attributes[_TOOL_BACKGROUND_TASK_ATTR],
                )
                with _TRACER.start_as_current_span(f"{component}:{tool_name}") as span:
                    _set_attributes(span, attributes)
                    try:
                        result = await func(*args, **kwargs)
                    except Exception as exc:
                        duration_ms = (perf_counter() - start) * 1000
                        span.set_attribute(_TOOL_DURATION_ATTR, duration_ms)
                        span.set_attribute(_TOOL_SUCCESS_ATTR, False)
                        span.set_attribute(_ERROR_TYPE_ATTR, type(exc).__name__)
                        span.set_status(Status(StatusCode.ERROR))
                        span.record_exception(exc)
                        logfire_exception(
                            "Tool failed",
                            tool_name=tool_name,
                            component=component,
                            duration_ms=duration_ms,
                            error_type=type(exc).__name__,
                        )
                        record_tool_result(
                            tool_name,
                            duration_ms,
                            status="error",
                            component=component,
                        )
                        raise

                    duration_ms = (perf_counter() - start) * 1000
                    span.set_attribute(_TOOL_DURATION_ATTR, duration_ms)
                    span.set_attribute(_TOOL_SUCCESS_ATTR, True)
                    span.set_status(Status(StatusCode.OK))
                    logfire_info(
                        "Tool completed",
                        tool_name=tool_name,
                        component=component,
                        duration_ms=duration_ms,
                        result_type=type(result).__name__,
                    )
                    record_tool_result(
                        tool_name,
                        duration_ms,
                        status="ok",
                        component=component,
                    )
                    return result

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = perf_counter()
            attributes = _tool_attributes(tool_name, component, args, kwargs)
            logfire_info(
                "Tool started",
                tool_name=tool_name,
                component=component,
                argument_count=attributes[_TOOL_ARGUMENT_COUNT_ATTR],
                background_task=attributes[_TOOL_BACKGROUND_TASK_ATTR],
            )
            with _TRACER.start_as_current_span(f"{component}:{tool_name}") as span:
                _set_attributes(span, attributes)
                try:
                    result = func(*args, **kwargs)
                except Exception as exc:
                    duration_ms = (perf_counter() - start) * 1000
                    span.set_attribute(_TOOL_DURATION_ATTR, duration_ms)
                    span.set_attribute(_TOOL_SUCCESS_ATTR, False)
                    span.set_attribute(_ERROR_TYPE_ATTR, type(exc).__name__)
                    span.set_status(Status(StatusCode.ERROR))
                    span.record_exception(exc)
                    logfire_exception(
                        "Tool failed",
                        tool_name=tool_name,
                        component=component,
                        duration_ms=duration_ms,
                        error_type=type(exc).__name__,
                    )
                    record_tool_result(
                        tool_name,
                        duration_ms,
                        status="error",
                        component=component,
                    )
                    raise

                duration_ms = (perf_counter() - start) * 1000
                span.set_attribute(_TOOL_DURATION_ATTR, duration_ms)
                span.set_attribute(_TOOL_SUCCESS_ATTR, True)
                span.set_status(Status(StatusCode.OK))
                logfire_info(
                    "Tool completed",
                    tool_name=tool_name,
                    component=component,
                    duration_ms=duration_ms,
                    result_type=type(result).__name__,
                )
                record_tool_result(
                    tool_name,
                    duration_ms,
                    status="ok",
                    component=component,
                )
                return result

        return sync_wrapper

    return decorator
