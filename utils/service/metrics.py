import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from opentelemetry import metrics as otel_metrics_api
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_configured = False
_config_lock = threading.Lock()

DEFAULT_TRACES_ENDPOINT = "http://observability:4318/v1/traces"
DEFAULT_METRICS_ENDPOINT = "http://observability:4318/v1/metrics"


def configure_metrics(
    service_name: str,
    traces_endpoint: str | None = None,
    metrics_endpoint: str | None = None,
    metric_export_interval_millis: int = 1000,
) -> None:
    global _configured

    with _config_lock:
        if _configured:
            return

        traces_endpoint = (
            traces_endpoint
            or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
            or DEFAULT_TRACES_ENDPOINT
        )

        metrics_endpoint = (
            metrics_endpoint
            or os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
            or DEFAULT_METRICS_ENDPOINT
        )

        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
            }
        )

        trace_provider = TracerProvider(resource=resource)
        trace_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=traces_endpoint),
            )
        )
        trace.set_tracer_provider(trace_provider)

        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=metrics_endpoint),
            export_interval_millis=metric_export_interval_millis,
        )

        otel_metrics_api.set_meter_provider(
            MeterProvider(
                resource=resource,
                metric_readers=[metric_reader],
            )
        )

        _configured = True


def get_tracer(name: str):
    return trace.get_tracer(name)


def get_meter(name: str):
    return otel_metrics_api.get_meter(name)


@dataclass(frozen=True)
class BaseServiceMetrics:
    # Counter
    events_total: Any

    # Histogram
    event_duration_ms: Any

    # Observable gauge
    queue_depth: Any | None


def create_base_service_metrics(
    meter_name: str = "base_service",
    observe_queue_depth: Callable[..., Iterable[Any]] | None = None,
) -> BaseServiceMetrics:
    meter = get_meter(meter_name)

    queue_depth = None

    if observe_queue_depth is not None:
        queue_depth = meter.create_observable_gauge(
            name="base_service.task_queue.depth",
            callbacks=[observe_queue_depth],
            description="Current number of queued tasks waiting in a subservice",
            unit="1",
        )

    return BaseServiceMetrics(
        events_total=meter.create_counter(
            name="base_service.events.total",
            description="Total number of subservice event executions by result",
            unit="1",
        ),
        event_duration_ms=meter.create_histogram(
            name="base_service.event.duration",
            description="Duration of a subservice event execution",
            unit="ms",
        ),
        queue_depth=queue_depth,
    )