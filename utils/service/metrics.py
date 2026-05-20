import os
import threading
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry import metrics as otel_metrics_api
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter


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

        resource = Resource.create({
            SERVICE_NAME: service_name,
        })

        trace_provider = TracerProvider(resource=resource)
        trace_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=traces_endpoint)
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
    orders_initialized: Any
    task_queue_size: Any
    events_runnable: Any
    events_started: Any
    events_completed: Any
    events_failed: Any
    validation_failed: Any
    cleanup_total: Any
    vector_clock_merges: Any
    vector_clock_merge_errors: Any
    outbound_rpc_total: Any
    outbound_rpc_failed: Any
    orchestrator_success_total: Any
    orchestrator_failure_total: Any
    orchestrator_notify_failed: Any


def create_base_service_metrics(
    meter_name: str = "base_service",
) -> BaseServiceMetrics:
    meter = get_meter(meter_name)

    return BaseServiceMetrics(
        orders_initialized=meter.create_counter(
            name="base_service.orders.initialized",
            description="Number of orders initialized in a subservice",
            unit="1",
        ),
        task_queue_size=meter.create_histogram(
            name="base_service.task_queue.size",
            description="Number of tasks created for an initialized order",
            unit="1",
        ),
        events_runnable=meter.create_counter(
            name="base_service.events.runnable",
            description="Number of runnable events returned by the subservice scheduler",
            unit="1",
        ),
        events_started=meter.create_counter(
            name="base_service.events.started",
            description="Number of subservice events started",
            unit="1",
        ),
        events_completed=meter.create_counter(
            name="base_service.events.completed",
            description="Number of subservice events completed successfully",
            unit="1",
        ),
        events_failed=meter.create_counter(
            name="base_service.events.failed",
            description="Number of subservice events failed with an exception",
            unit="1",
        ),
        validation_failed=meter.create_counter(
            name="base_service.validation.failed",
            description="Number of subservice events that returned an invalid validation response",
            unit="1",
        ),
        cleanup_total=meter.create_counter(
            name="base_service.cleanup.total",
            description="Number of cleanup operations",
            unit="1",
        ),
        vector_clock_merges=meter.create_counter(
            name="base_service.vector_clock.merges",
            description="Number of incoming vector-clock merges",
            unit="1",
        ),
        vector_clock_merge_errors=meter.create_counter(
            name="base_service.vector_clock.merge_errors",
            description="Number of vector-clock merge errors",
            unit="1",
        ),
        outbound_rpc_total=meter.create_counter(
            name="base_service.outbound_rpc.total",
            description="Number of outbound RPC calls made by a subservice",
            unit="1",
        ),
        outbound_rpc_failed=meter.create_counter(
            name="base_service.outbound_rpc.failed",
            description="Number of failed outbound RPC calls made by a subservice",
            unit="1",
        ),
        orchestrator_success_total=meter.create_counter(
            name="base_service.orchestrator.success_total",
            description="Number of successful checkout reports sent to orchestrator",
            unit="1",
        ),
        orchestrator_failure_total=meter.create_counter(
            name="base_service.orchestrator.failure_total",
            description="Number of failure checkout reports sent to orchestrator",
            unit="1",
        ),
        orchestrator_notify_failed=meter.create_counter(
            name="base_service.orchestrator.notify_failed",
            description="Number of failed attempts to notify orchestrator",
            unit="1",
        ),
    )