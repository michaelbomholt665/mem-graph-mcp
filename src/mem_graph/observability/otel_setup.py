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
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
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


def _provider_is_logfire(provider: object) -> bool:
    return provider.__class__.__module__.startswith("logfire.")


def _default_proxy_provider(provider: object, *, namespace: str) -> bool:
    return (
        provider.__class__.__name__ == "ProxyTracerProvider"
        and provider.__class__.__module__.startswith(namespace)
    )


def _default_proxy_meter_provider(provider: object) -> bool:
    return (
        provider.__class__.__name__ == "_ProxyMeterProvider"
        and provider.__class__.__module__.startswith("opentelemetry.metrics")
    )


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


def _build_resource(service_name: str, service_version: str) -> Resource:
    resource_attributes: dict[str, str] = {
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
    }
    environment = os.getenv("MEM_GRAPH_ENV") or os.getenv("ENV")
    if environment:
        resource_attributes[DEPLOYMENT_ENVIRONMENT] = environment
    return Resource.create(resource_attributes)


def _build_span_processors(state: ObservabilityState) -> list[BatchSpanProcessor]:
    processors: list[BatchSpanProcessor] = []
    if state.console_exporter:
        processors.append(BatchSpanProcessor(ConsoleSpanExporter(out=sys.stderr)))
    if state.otlp_configured:
        processors.append(BatchSpanProcessor(OTLPSpanExporter()))
    return processors


def _build_metric_readers(
    state: ObservabilityState,
) -> list[PeriodicExportingMetricReader]:
    readers: list[PeriodicExportingMetricReader] = []
    if state.console_exporter:
        readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter()))
    if state.otlp_configured:
        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
    return readers


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

        current_tracer_provider = trace.get_tracer_provider()
        if _provider_is_logfire(current_tracer_provider):
            logger.info("OpenTelemetry exporter setup delegated to Logfire bootstrap.")
            return state

        if not _default_proxy_provider(
            current_tracer_provider, namespace="opentelemetry.trace"
        ):
            logger.info(
                "OpenTelemetry provider already configured by %s; leaving it in place.",
                current_tracer_provider.__class__.__module__,
            )
            return state

        resource = _build_resource(state.service_name, state.service_version)
        tracer_provider = TracerProvider(resource=resource)
        for processor in _build_span_processors(state):
            tracer_provider.add_span_processor(processor)
        trace.set_tracer_provider(tracer_provider)

        metric_readers = _build_metric_readers(state)
        current_meter_provider = metrics.get_meter_provider()
        if metric_readers and _default_proxy_meter_provider(current_meter_provider):
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
    if _provider_is_logfire(tracer_provider):
        logger.debug(
            "Skipping standalone OpenTelemetry shutdown because Logfire owns the providers."
        )
        return
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
