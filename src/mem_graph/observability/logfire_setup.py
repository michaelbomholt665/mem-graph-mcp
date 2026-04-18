"""Central Logfire bootstrap for mem-graph."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Literal, cast

import logfire

from .otel_setup import _build_metric_readers, _build_span_processors
from .otel_setup import _resolve_state as _resolve_otel_state

logger = logging.getLogger(__name__)

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
    """Initialize Logfire once for the process."""
    global _STATE

    with _STATE_LOCK:
        if _STATE is not None:
            return _STATE

        state = _resolve_state(service_name, service_version)
        _STATE = state
        if not state.enabled:
            logger.info("Logfire disabled.")
            return state

        otel_state = _resolve_otel_state(service_name, service_version)
        additional_span_processors = _build_span_processors(otel_state)
        additional_readers = _build_metric_readers(otel_state)
        console: logfire.ConsoleOptions | Literal[False]
        console = (
            logfire.ConsoleOptions(
                show_project_link=False,
                min_log_level="info",
            )
            if state.console
            else cast(Literal[False], False)
        )
        metrics = (
            logfire.MetricsOptions(additional_readers=additional_readers)
            if additional_readers
            else None
        )

        logfire.configure(
            send_to_logfire=state.send_to_logfire,
            token=os.getenv("LOGFIRE_TOKEN") or None,
            service_name=service_name,
            service_version=service_version,
            environment=state.environment,
            console=console,
            metrics=metrics,
            scrubbing=logfire.ScrubbingOptions(
                extra_patterns=[r"bearer\s+[a-z0-9._=-]+"]
            ),
            inspect_arguments=False,
            additional_span_processors=additional_span_processors or None,
        )
        logfire.instrument_pydantic_ai(
            include_content=state.capture_content,
            version=3,
        )
        logfire.instrument_mcp()
        if state.instrument_httpx:
            logfire.instrument_httpx(capture_all=state.capture_httpx)

        _LOGFIRE.info(
            "Logfire bootstrap ready",
            service_name=service_name,
            service_version=service_version,
            environment=state.environment or "unknown",
            send_to_logfire=str(state.send_to_logfire),
            capture_content=state.capture_content,
            instrument_httpx=state.instrument_httpx,
            capture_httpx=state.capture_httpx,
            otel_exporters_attached=state.otel_exporters_attached,
        )
        logger.info(
            "Logfire enabled send_to_logfire=%s capture_content=%s instrument_httpx=%s capture_httpx=%s otel_exporters=%s",
            state.send_to_logfire,
            state.capture_content,
            state.instrument_httpx,
            state.capture_httpx,
            state.otel_exporters_attached,
        )
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
