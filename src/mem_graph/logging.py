#!/usr/bin/env python3
# src/mem_graph/logging.py
"""
logging.py — Hybrid logging for mem-graph (Console vs. JSON).

Configure once at startup via ``logging_setup_engine()``.
Supports two formats:
  - console: Human-readable, colourful logs (default if stderr is a TTY).
  - json: Structured JSON lines (default if stderr is redirected or LOG_FORMAT=json).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

from opentelemetry import trace


class _TraceContextFilter(logging.Filter):
    """Attach active trace context to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        span = trace.get_current_span()
        span_context = span.get_span_context() if span is not None else None
        if span_context is not None and span_context.is_valid:
            record.trace_id = f"{span_context.trace_id:032x}"
            record.span_id = f"{span_context.span_id:016x}"
        else:
            record.trace_id = "-"
            record.span_id = "-"
        return True


class _JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        data: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "-"),
            "span_id": getattr(record, "span_id", "-"),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        # Merge any extra fields attached via LogRecord.__dict__
        for key in ("tool", "duration_ms", "status", "code_length", "tools_called"):
            if key in record.__dict__:
                data[key] = record.__dict__[key]
        return json.dumps(data, ensure_ascii=False)


class _ConsoleFormatter(logging.Formatter):
    """Format log records for human readability with optional colours."""

    grey = "\x1b[38;20m"
    blue = "\x1b[34;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format_str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: blue + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset,
    }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno, self.format_str)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")

        # Add extra info if present
        result = formatter.format(record)
        extras = []
        for key in ("tool", "duration_ms", "status", "code_length", "tools_called"):
            if key in record.__dict__:
                val = record.__dict__[key]
                extras.append(f"{key}={val}")
        trace_id = getattr(record, "trace_id", "-")
        span_id = getattr(record, "span_id", "-")
        if trace_id != "-":
            extras.append(f"trace_id={trace_id}")
            extras.append(f"span_id={span_id}")

        if extras:
            result += f" {self.grey}({', '.join(extras)}){self.reset}"

        return result


def logging_setup_engine(level: str = "INFO") -> None:
    """
    Install a handler on the root logger. Defaults to human-readable 'console'
    format unless LOG_FORMAT=json is explicitly set.
    """
    log_format = os.getenv("LOG_FORMAT", "console")

    formatter: logging.Formatter
    if log_format == "json":
        formatter = _JsonFormatter()
    else:
        formatter = _ConsoleFormatter()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    handler.addFilter(_TraceContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


class logging_tool_span:
    """Async context manager that logs tool invocation timing."""

    def __init__(self, tool_name: str) -> None:
        self._name = tool_name
        self._start = 0.0
        self._logger = logging.getLogger("mem_graph.tools")

    async def __aenter__(self) -> "logging_tool_span":
        self._start = time.monotonic()
        return self

    async def __aexit__(self, exc_type: object, *_: object) -> None:
        duration_ms = round((time.monotonic() - self._start) * 1000, 1)
        status = "error" if exc_type else "ok"
        self._logger.info(
            "%s %s in %.1fms",
            self._name,
            status,
            duration_ms,
            extra={"tool": self._name, "duration_ms": duration_ms, "status": status},
        )


class logging_codegen_span:
    """Async context manager that logs CodeMode execute_code events."""

    def __init__(self, code: str, tools_called: list[str] | None = None) -> None:
        self._code = code
        self._tools_called = tools_called or []
        self._start = 0.0
        self._logger = logging.getLogger("mem_graph.codegen")

    async def __aenter__(self) -> "logging_codegen_span":
        self._start = time.monotonic()
        return self

    async def __aexit__(self, exc_type: object, *_: object) -> None:
        duration_ms = round((time.monotonic() - self._start) * 1000, 1)
        status = "error" if exc_type else "ok"
        self._logger.info(
            "codegen_execution %s in %.1fms",
            status,
            duration_ms,
            extra={
                "code_length": len(self._code),
                "tools_called": self._tools_called,
                "duration_ms": duration_ms,
                "status": status,
            },
        )
