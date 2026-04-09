import sys
import os

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

import grpc
from concurrent import futures
from logging.config import dictConfig
import logging

from fraud_detection import FraudDetectionProcess 

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

# Create a class to define the server functions, derived from
# fraud_detection_pb2_grpc.HelloServiceServicer
# class HelloService(fraud_detection_grpc.HelloServiceServicer):
#     # Create an RPC function to say hello
#     def SayHello(self, request, context):
#         # Create a HelloResponse object
#         response = fraud_detection.HelloResponse()
#         # Set the greeting field of the response object
#         response.greeting = "Hello, " + request.name
#         # Print the greeting message
#         print(response.greeting)
#         # Return the response object
#         return response

class FraudDetectionService(fraud_detection_grpc.FraudDetectionServiceServicer):
    def __init__(self):
        self.fraudDetectionProcess = FraudDetectionProcess()
        background_executor.submit(self.worker, self.userDataProcess)

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
        self.fraudDetectionProcess.initialize_order(request.id, request.order)
        return fraud_detection.InitOrderResponse(ok=True)

    def UpdateStatus(self, request, context):
        logger.info(
            "Received UpdateStatus request for transaction %s",
            request.id,
        )

        if request.id not in self.fraudDetectionProcess.orders:
            return fraud_detection.StatusUpdateResponse(
                ok=False,
                message="Order ID not found. Please initialize the order first."
            )

        incoming_vc = tuple([
            request.TransactionServiceA,
            request.TransactionServiceB,
            request.FraudDetection,
            request.Suggestions
        ])

        logger.debug(
            "Merging VC for transaction %s into both services: %s",
            request.id,
            incoming_vc
        )

        self.fraudDetectionProcess.update_with_incoming_vector_clock(request.id, incoming_vc)

        return fraud_detection.StatusUpdateResponse(
            ok=True,
            message="Status updated successfully"
        )


def serve():
    # Create a gRPC server
    server = grpc.server(futures.ThreadPoolExecutor())
    # Add HelloService
    fraud_detection_grpc.add_FraudDetectionServiceServicer_to_server(FraudDetectionService(), server)
    # Listen on port 50051
    port = "50051"
    server.add_insecure_port("[::]:" + port)
    # Start the server
    server.start()
    logger.info("Server started. Listening on port 50051.")
    # Keep thread alive
    server.wait_for_termination()

if __name__ == '__main__':
    serve()