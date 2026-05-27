import os
import sys
import logging
import threading
from logging.config import dictConfig
from concurrent import futures

import grpc
from opentelemetry.instrumentation.grpc import server_interceptor


FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")


def add_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)


add_path("../../../utils/service")
add_path("../../../utils/pb/transaction_verification")

from metrics import configure_metrics, get_tracer
from verification_metrics import create_verification_metrics

from interceptors import LoggingInterceptor
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

from card_books_verification import CardBookVerificationProcess
from user_verification import UserVerificationProcess

rpc_executor = futures.ThreadPoolExecutor(max_workers=10)
background_executor = futures.ThreadPoolExecutor(max_workers=20)

dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        }
    },
    'handlers': {
        'grpc': {
            'class': 'logging.StreamHandler',
            'stream': sys.stderr,   # Equivalent to Flask wsgi_errors_stream
            'formatter': 'default',
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['grpc']
    }
})

logger = logging.getLogger(__name__)

APP_SERVICE_NAME = os.getenv(
    "OTEL_SERVICE_NAME",
    "transaction-verification-service",
)

configure_metrics(service_name=APP_SERVICE_NAME)

tracer = get_tracer(__name__)
verification_metrics = create_verification_metrics()

lock = threading.Lock()
condition = threading.Condition(lock)


# Create a class to define the server functions, derived from
# transaction_verification.VerificationServiceServicer
class VerificationService(transaction_verification_grpc.VerificationServiceServicer):

    def __init__(self):
        self.userVerification = UserVerificationProcess(
            app_service_name=APP_SERVICE_NAME,
        )
        self.cardBookVerification = CardBookVerificationProcess(
            app_service_name=APP_SERVICE_NAME,
        )

        background_executor.submit(self.worker, self.userVerification)
        background_executor.submit(self.worker, self.cardBookVerification)

    def worker(self, service):
        cond = service.condition

        while True:
            try:
                with cond:
                    cond.wait_for(service.has_events_to_run)
                    events = service.get_events_to_run()
                    verification_metrics.event_batch_size.record(
                        len(events),
                        {
                            "verification.service": service.__class__.__name__,
                        },
                    )

                logger.debug(
                    "Worker got %d events for %s",
                    len(events),
                    service.__class__.__name__,
                )

                for event in events:
                    action_name = getattr(event.action, "__name__", repr(event.action))

                    with tracer.start_as_current_span("VerificationService.schedule_event") as span:
                        span.set_attribute("event.id", event.id)
                        span.set_attribute("event.action", action_name)
                        span.set_attribute("event.required_vc", str(event.required_vc))
                        span.set_attribute("verification.service", service.__class__.__name__)

                        verification_metrics.events_scheduled.add(
                            1,
                            {
                                "verification.service": service.__class__.__name__,
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
                verification_metrics.worker_errors.add(
                    1,
                    {
                        "verification.service": service.__class__.__name__,
                    },
                )
                logger.exception("Worker crashed for %s", service.__class__.__name__)
                raise
   
    def InitOrder(self, request, context):
        with tracer.start_as_current_span("VerificationService.InitOrder") as span:
            span.set_attribute("transaction.id", request.id)

            verification_metrics.init_order_requests.add(
                1,
                {
                    "rpc.method": "InitOrder",
                },
            )

            logger.info(f"Received InitOrder request for transaction {request.id}")

            self.cardBookVerification.initialize_order(request.id, request.order)
            self.userVerification.initialize_order(request.id, request.order)

            return transaction_verification.InitOrderResponse(ok=True)
    

def serve():
    # Create a gRPC server
    server = grpc.server(
        rpc_executor,
        interceptors=[
            server_interceptor(),
            LoggingInterceptor(),
        ],
    )
    # Add VerificationService
    transaction_verification_grpc.add_VerificationServiceServicer_to_server(VerificationService(), server)
    # Listen on port 50052
    port = "50052"
    server.add_insecure_port("[::]:" + port)
    # Start the server
    server.start()
    logger.info("Server started. Listening on port 50052.")
    # Keep thread alive
    server.wait_for_termination()

if __name__ == '__main__':
    serve()