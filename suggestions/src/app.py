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


add_path("../../../utils/pb/suggestion")
add_path("../../../utils/service")

from metrics import configure_metrics, get_tracer
from interceptors import LoggingInterceptor

import suggestion_pb2 as suggestion
import suggestion_pb2_grpc as suggestion_grpc

from book_suggestion import BookSuggestionProcess
from suggestion_metrics import create_suggestion_metrics


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
    "suggestion-service",
)

# The provider/exporter setup lives in utils/service/metrics.py.
# This should be called once per Python process before creating tracers/meters.
configure_metrics(service_name=APP_SERVICE_NAME)

tracer = get_tracer(__name__)
suggestion_metrics = create_suggestion_metrics()


class SuggestionService(suggestion_grpc.SuggestionServiceServicer):
    def __init__(self):
        # Keep this compatible with both constructor styles:
        #   BookSuggestionProcess()
        #   BookSuggestionProcess(app_service_name=...)
        try:
            self.bookSuggestion = BookSuggestionProcess(
                app_service_name=APP_SERVICE_NAME,
            )
        except TypeError:
            self.bookSuggestion = BookSuggestionProcess()

        background_executor.submit(self.worker, self.bookSuggestion)

    def worker(self, service):
        cond = service.condition

        while True:
            try:
                with cond:
                    cond.wait_for(service.has_events_to_run)
                    events = service.get_events_to_run()

                    suggestion_metrics.event_batch_size.record(
                        len(events),
                        {
                            "suggestion.service": service.__class__.__name__,
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
                        "SuggestionService.schedule_event"
                    ) as span:
                        span.set_attribute("event.id", event.id)
                        span.set_attribute("event.action", action_name)
                        span.set_attribute("event.required_vc", str(event.required_vc))
                        span.set_attribute(
                            "suggestion.service",
                            service.__class__.__name__,
                        )

                        suggestion_metrics.events_scheduled.add(
                            1,
                            {
                                "suggestion.service": service.__class__.__name__,
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
                suggestion_metrics.worker_errors.add(
                    1,
                    {
                        "suggestion.service": service.__class__.__name__,
                    },
                )
                logger.exception("Worker crashed for %s", service.__class__.__name__)
                raise

    def InitOrder(self, request, context):
        attrs = {
            "rpc.method": "InitOrder",
        }

        with tracer.start_as_current_span("SuggestionService.InitOrder") as span:
            span.set_attribute("transaction.id", request.id)

            suggestion_metrics.init_order_requests.add(1, attrs)

            logger.info("Received InitOrder request for transaction %s", request.id)

            self.bookSuggestion.initialize_order(request.id, request.order)

            return suggestion.InitOrderResponse(ok=True)

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

        with tracer.start_as_current_span("SuggestionService.UpdateStatus") as span:
            span.set_attribute("transaction.id", request.id)
            span.set_attribute("incoming_vc", str(incoming_vc))

            suggestion_metrics.update_status_requests.add(1, attrs)

            logger.info(
                "Received UpdateStatus request for transaction %s",
                request.id,
            )

            with self.bookSuggestion.state as state:
                order_exists = request.id in state.orders

            span.set_attribute("order.exists", order_exists)

            if not order_exists:
                suggestion_metrics.update_status_rejected.add(
                    1,
                    {
                        **attrs,
                        "reason": "order_not_found",
                    },
                )

                return suggestion.StatusUpdateResponse(
                    ok=False,
                    message="Order ID not found. Please initialize the order first.",
                )

            logger.debug(
                "Merging VC for transaction %s into BookSuggestionProcess: %s",
                request.id,
                incoming_vc,
            )

            self.bookSuggestion.update_with_incoming_vector_clock(
                request.id,
                incoming_vc,
            )

            suggestion_metrics.update_status_success.add(1, attrs)

            return suggestion.StatusUpdateResponse(
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

    suggestion_grpc.add_SuggestionServiceServicer_to_server(
        SuggestionService(),
        server,
    )

    port = "50053"
    server.add_insecure_port("[::]:" + port)
    server.start()

    logger.info("Server started. Listening on port %s.", port)

    server.wait_for_termination()


if __name__ == "__main__":
    serve()
