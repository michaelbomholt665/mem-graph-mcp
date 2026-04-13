"""Central OpenTelemetry bootstrap for mem-graph."""

from __future__ import annotations

import logging
import os
import sys
import threading
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)

_STATE_LOCK = threading.Lock()
_STATE: "ObservabilityState | None" = None


@dataclass(frozen=True, slots=True)
class ObservabilityState:
    """Resolved OpenTelemetry configuration for the current process."""

    enabled: bool
    service_name: str
    service_version: str
    console_exporter: bool
    otlp_configured: bool


def _bool_env(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _otlp_configured() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        )
    )


def _console_exporter_enabled(*, enabled: bool, otlp_configured: bool) -> bool:
    raw = os.getenv("MEM_GRAPH_OTEL_CONSOLE_EXPORTER")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return enabled and not otlp_configured


def _resolve_state(service_name: str, service_version: str) -> ObservabilityState:
    if _bool_env("OTEL_SDK_DISABLED"):
        return ObservabilityState(
            enabled=False,
            service_name=service_name,
            service_version=service_version,
            console_exporter=False,
            otlp_configured=False,
        )

    otlp_configured = _otlp_configured()
    enabled = _bool_env(
        "MEM_GRAPH_OTEL_ENABLED",
        default=otlp_configured or _bool_env("MEM_GRAPH_OTEL_CONSOLE_EXPORTER"),
    )

    return ObservabilityState(
        enabled=enabled,
        service_name=service_name,
        service_version=service_version,
        console_exporter=_console_exporter_enabled(
            enabled=enabled,
            otlp_configured=otlp_configured,
        ),
        otlp_configured=otlp_configured,
    )


def setup_observability(
    *,
    service_name: str,
    service_version: str,
) -> ObservabilityState:
    """Initialize OpenTelemetry once for the process."""
    global _STATE

    with _STATE_LOCK:
        if _STATE is not None:
            return _STATE

        state = _resolve_state(service_name, service_version)
        _STATE = state
        if not state.enabled:
            logger.info("OpenTelemetry disabled.")
            return state

        resource_attributes: dict[str, str] = {
            SERVICE_NAME: state.service_name,
            SERVICE_VERSION: state.service_version,
        }
        environment = os.getenv("MEM_GRAPH_ENV") or os.getenv("ENV")
        if environment:
            resource_attributes[DEPLOYMENT_ENVIRONMENT] = environment

        resource = Resource.create(resource_attributes)

        tracer_provider = TracerProvider(resource=resource)
        if state.console_exporter:
            tracer_provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter(out=sys.stderr))
            )
        if state.otlp_configured:
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

        metric_readers = []
        if state.console_exporter:
            metric_readers.append(
                PeriodicExportingMetricReader(ConsoleMetricExporter())
            )
        if state.otlp_configured:
            metric_readers.append(
                PeriodicExportingMetricReader(OTLPMetricExporter())
            )
        if metric_readers:
            metrics.set_meter_provider(
                MeterProvider(resource=resource, metric_readers=metric_readers)
            )

        logger.info(
            "OpenTelemetry enabled service=%s console_exporter=%s otlp_exporter=%s",
            state.service_name,
            state.console_exporter,
            state.otlp_configured,
        )
        return state


def shutdown_observability() -> None:
    """Flush telemetry exporters during graceful shutdown."""
    state = _STATE
    if state is None or not state.enabled:
        return

    tracer_provider = trace.get_tracer_provider()
    meter_provider = metrics.get_meter_provider()

    try:
        force_flush = getattr(tracer_provider, "force_flush", None)
        if callable(force_flush):
            force_flush()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to flush tracer provider: %s", exc)

    try:
        shutdown = getattr(tracer_provider, "shutdown", None)
        if callable(shutdown):
            shutdown()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to shut down tracer provider: %s", exc)

    try:
        shutdown = getattr(meter_provider, "shutdown", None)
        if callable(shutdown):
            shutdown()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to shut down meter provider: %s", exc)