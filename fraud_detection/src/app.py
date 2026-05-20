import logging
import os
import sys
from concurrent import futures
from logging.config import dictConfig

import grpc
from opentelemetry.instrumentation.grpc import server_interceptor


# This set of lines is needed to import the gRPC stubs and shared service utilities.
# The paths are relative to this file, or absolute inside the container.
FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")


def add_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)


add_path("../../../utils/pb/fraud_detection")
add_path("../../../utils/service")

from metrics import configure_metrics, get_tracer
from interceptors import LoggingInterceptor

import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

from fraud_detection import FraudDetectionProcess
from fraud_detection_metrics import create_fraud_detection_metrics


rpc_executor = futures.ThreadPoolExecutor(max_workers=10)
background_executor = futures.ThreadPoolExecutor(max_workers=20)


dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "grpc": {
                "class": "logging.StreamHandler",
                "stream": sys.stderr,
                "formatter": "default",
            }
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["grpc"],
        },
    }
)

logger = logging.getLogger(__name__)


APP_SERVICE_NAME = os.getenv(
    "OTEL_SERVICE_NAME",
    "fraud-detection-service",
)

# The provider/exporter setup lives in utils/service/metrics.py.
# This should be called once per Python process before creating tracers/meters.
configure_metrics(service_name=APP_SERVICE_NAME)

tracer = get_tracer(__name__)
fraud_metrics = create_fraud_detection_metrics()


class FraudDetectionService(fraud_detection_grpc.FraudDetectionServiceServicer):
    def __init__(self):
        # Keep this compatible with both constructor styles:
        #   FraudDetectionProcess()
        #   FraudDetectionProcess(app_service_name=...)
        try:
            self.fraudDetectionProcess = FraudDetectionProcess(
                app_service_name=APP_SERVICE_NAME,
            )
        except TypeError:
            self.fraudDetectionProcess = FraudDetectionProcess()

        background_executor.submit(self.worker, self.fraudDetectionProcess)

    def worker(self, service):
        cond = service.condition

        while True:
            try:
                with cond:
                    cond.wait_for(service.has_events_to_run)
                    events = service.get_events_to_run()

                    fraud_metrics.event_batch_size.record(
                        len(events),
                        {
                            "fraud.service": service.__class__.__name__,
                        },
                    )

                logger.debug(
                    "Worker got %d events for %s",
                    len(events),
                    service.__class__.__name__,
                )

                for event in events:
                    action_name = getattr(event.action, "__name__", repr(event.action))

                    with tracer.start_as_current_span(
                        "FraudDetectionService.schedule_event"
                    ) as span:
                        span.set_attribute("event.id", event.id)
                        span.set_attribute("event.action", action_name)
                        span.set_attribute("event.required_vc", str(event.required_vc))
                        span.set_attribute("fraud.service", service.__class__.__name__)

                        fraud_metrics.events_scheduled.add(
                            1,
                            {
                                "fraud.service": service.__class__.__name__,
                                "event.action": action_name,
                            },
                        )

                        logger.debug(
                            "[%s] Event %s is starting, required_vc=%s",
                            event.id,
                            action_name,
                            event.required_vc,
                        )

                        background_executor.submit(event.action, event.id)

            except Exception:
                fraud_metrics.worker_errors.add(
                    1,
                    {
                        "fraud.service": service.__class__.__name__,
                    },
                )
                logger.exception("Worker crashed for %s", service.__class__.__name__)
                raise

    def InitOrder(self, request, context):
        attrs = {
            "rpc.method": "InitOrder",
        }

        with tracer.start_as_current_span("FraudDetectionService.InitOrder") as span:
            span.set_attribute("transaction.id", request.id)

            fraud_metrics.init_order_requests.add(1, attrs)

            logger.info("Received InitOrder request for transaction %s", request.id)

            self.fraudDetectionProcess.initialize_order(request.id, request.order)

            return fraud_detection.InitOrderResponse(ok=True)

    def UpdateStatus(self, request, context):
        attrs = {
            "rpc.method": "UpdateStatus",
        }

        incoming_vc = (
            request.TransactionServiceA,
            request.TransactionServiceB,
            request.FraudDetection,
            request.Suggestions,
        )

        with tracer.start_as_current_span("FraudDetectionService.UpdateStatus") as span:
            span.set_attribute("transaction.id", request.id)
            span.set_attribute("incoming_vc", str(incoming_vc))

            fraud_metrics.update_status_requests.add(1, attrs)

            logger.info(
                "Received UpdateStatus request for transaction %s",
                request.id,
            )

            with self.fraudDetectionProcess.state as state:
                order_exists = request.id in state.orders

            span.set_attribute("order.exists", order_exists)

            if not order_exists:
                fraud_metrics.update_status_rejected.add(
                    1,
                    {
                        **attrs,
                        "reason": "order_not_found",
                    },
                )

                return fraud_detection.StatusUpdateResponse(
                    ok=False,
                    message="Order ID not found. Please initialize the order first.",
                )

            logger.debug(
                "Merging VC for transaction %s into FraudDetectionProcess: %s",
                request.id,
                incoming_vc,
            )

            self.fraudDetectionProcess.update_with_incoming_vector_clock(
                request.id,
                incoming_vc,
            )

            self.fraudDetectionProcess.update_vector_clock(request.id)

            fraud_metrics.update_status_success.add(1, attrs)

            return fraud_detection.StatusUpdateResponse(
                ok=True,
                message="Status updated successfully",
            )


def serve():
    server = grpc.server(
        rpc_executor,
        interceptors=[
            server_interceptor(),
            LoggingInterceptor(),
        ],
    )

    fraud_detection_grpc.add_FraudDetectionServiceServicer_to_server(
        FraudDetectionService(),
        server,
    )

    port = "50051"
    server.add_insecure_port("[::]:" + port)
    server.start()

    logger.info("Server started. Listening on port %s.", port)

    server.wait_for_termination()


if __name__ == "__main__":
    serve()
