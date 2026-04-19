"""Central Logfire bootstrap for mem-graph."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Literal, cast

import logfire

from .otel_setup import _build_metric_readers
from .otel_setup import _resolve_state as _resolve_otel_state

logger = logging.getLogger(__name__)

_ConsoleLevel = Literal[
    "trace",
    "debug",
    "info",
    "notice",
    "warn",
    "warning",
    "error",
    "fatal",
]

_STATE_LOCK = threading.Lock()
_STATE: "LogfireState | None" = None
_LOGFIRE = logfire.with_tags("mem_graph")


@dataclass(frozen=True, slots=True)
class LogfireState:
    """Resolved Logfire configuration for the current process."""

    enabled: bool
    send_to_logfire: bool | Literal["if-token-present"]
    console: bool
    token_present: bool
    capture_content: bool
    instrument_httpx: bool
    capture_httpx: bool
    environment: str | None
    otel_exporters_attached: bool


def _bool_env(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_send_to_logfire() -> bool | Literal["if-token-present"]:
    raw = os.getenv("MEM_GRAPH_LOGFIRE_SEND_TO_LOGFIRE")
    if raw is None:
        raw = os.getenv("LOGFIRE_SEND_TO_LOGFIRE")
    if raw is None:
        return "if-token-present"

    normalized = raw.strip().lower()
    if normalized == "if-token-present":
        return "if-token-present"
    return normalized in {"1", "true", "yes", "on"}


def _resolve_environment() -> str | None:
    return (
        os.getenv("MEM_GRAPH_ENV")
        or os.getenv("ENV")
        or os.getenv("LOGFIRE_ENVIRONMENT")
    )


def _console_min_level() -> _ConsoleLevel:
    raw = os.getenv("MEM_GRAPH_LOGFIRE_CONSOLE_MIN_LEVEL", "warning").strip().lower()
    if raw in {"trace", "debug", "info", "notice", "warn", "warning", "error", "fatal"}:
        return cast(_ConsoleLevel, raw)
    return "warning"


def _resolve_state(service_name: str, service_version: str) -> LogfireState:
    otel_state = _resolve_otel_state(service_name, service_version)
    token_present = bool((os.getenv("LOGFIRE_TOKEN") or "").strip())
    enabled = _bool_env(
        "MEM_GRAPH_LOGFIRE_ENABLED",
        default=token_present
        or _bool_env("MEM_GRAPH_LOGFIRE_CONSOLE")
        or otel_state.enabled,
    )
    console = _bool_env(
        "MEM_GRAPH_LOGFIRE_CONSOLE",
        default=enabled and not token_present and not otel_state.enabled,
    )

    return LogfireState(
        enabled=enabled,
        send_to_logfire=_resolve_send_to_logfire(),
        console=console,
        token_present=token_present,
        capture_content=_bool_env("MEM_GRAPH_LOGFIRE_INCLUDE_CONTENT"),
        instrument_httpx=_bool_env("MEM_GRAPH_LOGFIRE_INSTRUMENT_HTTPX", default=True),
        capture_httpx=_bool_env("MEM_GRAPH_LOGFIRE_CAPTURE_HTTPX"),
        environment=_resolve_environment(),
        otel_exporters_attached=otel_state.enabled,
    )


def _sanitize_attributes(
    attributes: dict[str, object] | None,
) -> dict[str, str | bool | int | float]:
    clean: dict[str, str | bool | int | float] = {}
    if not attributes:
        return clean

    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            clean[key] = value
        else:
            clean[key] = str(value)

    return clean


def setup_logfire(
    *,
    service_name: str,
    service_version: str,
) -> LogfireState:
    """Initialize Logfire, hardened for MCP stdio transport."""
    global _STATE

    with _STATE_LOCK:
        if _STATE is not None:
            return _STATE

        state = _resolve_state(service_name, service_version)
        _STATE = state

        # 1. Determine if we are running in the Copilot CLI (stdio)
        is_stdio = os.getenv("TRANSPORT", "stdio") == "stdio"

        # 2. Redirect standard python logging to stderr immediately.
        import sys

        logging.basicConfig(stream=sys.stderr, level=logging.INFO)

        if not state.enabled:
            return state

        otel_state = _resolve_otel_state(service_name, service_version)

        # 3. Force console=False if we are on stdio transport.
        console: logfire.ConsoleOptions | Literal[False] = False
        if not is_stdio and state.console:
            console = logfire.ConsoleOptions(
                show_project_link=False,
                min_log_level=_console_min_level(),
            )

        # 4. Correct Metrics Configuration
        # MetricsOptions usually only takes 'collect_in_spans'.
        # Custom readers are typically passed to logfire.configure directly
        # via a 'metrics' argument if it's a dict or specialized object.
        metric_readers = _build_metric_readers(otel_state)

        # If is_stdio is True, we want NO metrics output to avoid stdout pollution.
        metrics_config = None
        if not is_stdio and metric_readers:
            # Check your Logfire version; most use a dict or omit MetricsOptions for readers
            metrics_config = logfire.MetricsOptions(collect_in_spans=True)

        logfire.configure(
            send_to_logfire=state.send_to_logfire,
            token=os.getenv("LOGFIRE_TOKEN") or None,
            service_name=service_name,
            service_version=service_version,
            environment=state.environment,
            console=console,
            metrics=metrics_config,  # Corrected
            scrubbing=logfire.ScrubbingOptions(
                extra_patterns=[r"bearer\s+[a-z0-9._=-]+"]
            ),
            inspect_arguments=False,
            # If your build supports additional_readers, pass them here:
            # additional_readers=metric_readers if not is_stdio else None,
        )

        # 5. Instrument and Silent Ready Log
        logfire.instrument_pydantic_ai(include_content=state.capture_content, version=3)
        logfire.instrument_mcp()

        # Log only to stderr to keep the MCP handshake clean.
        logging.getLogger(__name__).info("Logfire bootstrap ready (via stderr)")

        return state


def logfire_enabled() -> bool:
    """Return whether Logfire is active for this process."""
    return bool(_STATE and _STATE.enabled)


def logfire_debug(msg_template: str, /, **attributes: object) -> None:
    """Emit a structured debug event when Logfire is enabled."""
    if not logfire_enabled():
        return
    logfire_instance = cast(Any, _LOGFIRE)
    logfire_instance.log(
        "debug",
        msg_template,
        attributes=_sanitize_attributes(attributes),
    )


def logfire_info(msg_template: str, /, **attributes: object) -> None:
    """Emit a structured info event when Logfire is enabled."""
    if not logfire_enabled():
        return
    logfire_instance = cast(Any, _LOGFIRE)
    logfire_instance.log(
        "info",
        msg_template,
        attributes=_sanitize_attributes(attributes),
    )


def logfire_exception(msg_template: str, /, **attributes: object) -> None:
    """Emit a structured error event with exception context when enabled."""
    if not logfire_enabled():
        return
    logfire_instance = cast(Any, _LOGFIRE)
    logfire_instance.log(
        "error",
        msg_template,
        attributes=_sanitize_attributes(attributes),
        exc_info=True,
    )


def shutdown_logfire() -> None:
    """Flush Logfire telemetry during graceful shutdown."""
    state = _STATE
    if state is None or not state.enabled:
        return

    try:
        logfire.force_flush(3000)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to flush Logfire: %s", exc)

    try:
        logfire.shutdown()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to shut down Logfire: %s", exc)
