from dataclasses import dataclass
from typing import Any

from opentelemetry import metrics


@dataclass
class VerificationMetrics:
    init_order_requests: Any
    event_batch_size: Any
    events_scheduled: Any
    worker_errors: Any


def create_verification_metrics() -> VerificationMetrics:
    meter = metrics.get_meter("transaction-verification")

    return VerificationMetrics(
        init_order_requests=meter.create_counter(
            name="verification.init_order.requests",
            description="Number of InitOrder requests received",
            unit="1",
        ),
        event_batch_size=meter.create_histogram(
            name="verification.worker.event_batch_size",
            description="Number of runnable events pulled by a worker loop",
            unit="1",
        ),
        events_scheduled=meter.create_counter(
            name="verification.events.scheduled",
            description="Number of verification events scheduled for background execution",
            unit="1",
        ),
        worker_errors=meter.create_counter(
            name="verification.worker.errors",
            description="Number of verification worker loop errors",
            unit="1",
        ),
    )