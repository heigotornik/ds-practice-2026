from dataclasses import dataclass
from typing import Any

from opentelemetry import metrics


@dataclass
class FraudDetectionMetrics:
    init_order_requests: Any
    update_status_requests: Any
    update_status_success: Any
    update_status_rejected: Any
    event_batch_size: Any
    events_scheduled: Any
    worker_errors: Any


def create_fraud_detection_metrics() -> FraudDetectionMetrics:
    """
    Fraud-detection-specific metric instruments.

    OpenTelemetry provider/exporter configuration must stay in utils/service/metrics.py.
    This file only creates counters and histograms from the already configured global meter provider.
    """
    meter = metrics.get_meter("fraud-detection")

    return FraudDetectionMetrics(
        init_order_requests=meter.create_counter(
            name="fraud_detection.init_order.requests",
            description="Number of InitOrder requests received by fraud detection",
            unit="1",
        ),
        update_status_requests=meter.create_counter(
            name="fraud_detection.update_status.requests",
            description="Number of UpdateStatus requests received by fraud detection",
            unit="1",
        ),
        update_status_success=meter.create_counter(
            name="fraud_detection.update_status.success",
            description="Number of successful UpdateStatus requests handled by fraud detection",
            unit="1",
        ),
        update_status_rejected=meter.create_counter(
            name="fraud_detection.update_status.rejected",
            description="Number of rejected UpdateStatus requests handled by fraud detection",
            unit="1",
        ),
        event_batch_size=meter.create_histogram(
            name="fraud_detection.worker.event_batch_size",
            description="Number of runnable events pulled by the fraud-detection worker loop",
            unit="1",
        ),
        events_scheduled=meter.create_counter(
            name="fraud_detection.events.scheduled",
            description="Number of fraud-detection events scheduled for background execution",
            unit="1",
        ),
        worker_errors=meter.create_counter(
            name="fraud_detection.worker.errors",
            description="Number of fraud-detection worker loop errors",
            unit="1",
        ),
    )
