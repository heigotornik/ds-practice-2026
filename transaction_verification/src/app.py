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
        
        self.userVerificationCondition = self.userVerification.get_condition() 
        self.cardBookCondition = self.cardBookVerification.get_condition()  

        background_executor.submit(self.worker, self.userVerification)
        background_executor.submit(self.worker, self.cardBookVerification)

    def worker(self, service):
        cond = service.get_condition()
        with cond:
            while True:
                logger.debug("Worker for %s is waiting for condition", service.__class__.__name__)
                while len(service.get_events_to_run()) == 0:
                    cond.wait()
                events = service.get_events_to_run()
                logger.debug("Worker for %s woke up and found %d events to run", service.__class__.__name__, len(events))
                for event in events:
                    background_executor.submit(event.action, event.id)
                cond.notify_all()
   
    def InitOrder(self, request, context):
        logger.info(f"Received InitOrder request for transaction {request.id}")
        self.cardBookVerification.initialize_order(request.id, request.order)
        self.userVerification.initialize_order(request.id, request.order)
        return transaction_verification.InitOrderResponse(ok=True)
    
    def UpdateStatus(self, request, context):
        logger.info(f"Received UpdateStatus request for transaction {request.id} with status {request.status}")
        if request.id not in self.orders:
            return transaction_verification.UpdateStatusResponse(ok=False, message="Order ID not found. Please initialize the order first.")
        
        logger.debug(f"Updating status for transaction {request.id} to {request.status}")
        return transaction_verification.UpdateStatusResponse(ok=True, message="Status updated successfully")



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