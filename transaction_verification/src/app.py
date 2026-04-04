import re
import sys
import os
import sys
from logging.config import dictConfig
import logging
import threading
from typing import List

from subservice import RunnableEvent

from card_books_verification import CardBookVerificationProcess

from user_verification import UserVerificationProcess

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
from interceptors import LoggingInterceptor
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc


import grpc
from concurrent import futures


rpc_executor = futures.ThreadPoolExecutor(max_workers=10)
background_executor = futures.ThreadPoolExecutor(max_workers=4)

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


lock = threading.Lock()
condition = threading.Condition(lock)


# Create a class to define the server functions, derived from
# transaction_verification.VerificationServiceServicer
class VerificationService(transaction_verification_grpc.VerificationServiceServicer):

    def __init__(self):
        self.userVerification = UserVerificationProcess()
        self.cardBookVerification = CardBookVerificationProcess()

        background_executor.submit(self.worker, self.userVerification)
        background_executor.submit(self.worker, self.cardBookVerification)

    def worker(self, service):
        cond = service.condition

        while True:
            try:
                with cond:
                    cond.wait_for(lambda: len(service.get_events_to_run()) > 0)
                    events = service.get_events_to_run()

                logger.debug("Worker got %d events for %s", len(events), service.__class__.__name__)

                for event in events:
                    service.add_task_running(event.id)
                    background_executor.submit(event.action, event.id)
            except Exception:
                logger.exception("Worker crashed for %s", service.__class__.__name__)
                raise
   
    def InitOrder(self, request, context):
        logger.info(f"Received InitOrder request for transaction {request.id}")
        self.cardBookVerification.initialize_order(request.id, request.order)
        self.userVerification.initialize_order(request.id, request.order)
        return transaction_verification.InitOrderResponse(ok=True)
    
    def UpdateStatus(self, request, context):
        logger.info(
            "Received UpdateStatus request for transaction %s with vc=%s",
            request.id,
            request.vc
        )

        if request.id not in self.userVerification.orders and \
        request.id not in self.cardBookVerification.orders:
            return transaction_verification.UpdateStatusResponse(
                ok=False,
                message="Order ID not found. Please initialize the order first."
            )

        incoming_vc = tuple(request.vc)

        logger.debug(
            "Merging VC for transaction %s into both services: %s",
            request.id,
            incoming_vc
        )

        self.userVerification.update_with_incoming_vector_clock(request.id, incoming_vc)
        self.cardBookVerification.update_with_incoming_vector_clock(request.id, incoming_vc)

        return transaction_verification.UpdateStatusResponse(
            ok=True,
            message="Status updated successfully"
        )



def serve():
    # Create a gRPC server
    server = grpc.server(rpc_executor,
                         interceptors=[LoggingInterceptor()])
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