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
import threading

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

background_executor = futures.ThreadPoolExecutor(max_workers=4)
class FraudDetectionService(fraud_detection_grpc.FraudDetectionServiceServicer):
    def __init__(self, svc_idx = 0, total_svcs = 3):
        self.svc_idx = svc_idx
        self.total_svcs = total_svcs
        self._lock = threading.Lock()
        self.orders = {}
        self.orderIds = []
        self.eventClocks = {
            (0, 2, 1, 0) : self.DetectFraud
        }
        background_executor.submit(self.checkClocks)

    def checkClocks(self):
        while True:
            for i in range(len(self.orderIds)):
                clock = tuple(self.orders[self.orderIds[i]]["vc"])
                if clock in self.eventClocks:
                    background_executor.submit(self.eventClocks[clock], i)

    def InitOrder(self, request, context):
        logger.info(f"Received InitOrder request for transaction {request.id}")
        self.orders[request.id] = {"data": request.order, "vc": [0] * self.total_svcs}
        self.orderIds.append(request.id)
        return fraud_detection.InitOrderResponse(ok=True)

    def merge_and_increment(self, local_vc, incoming_vc):
        for i in range(self.total_svcs):
            local_vc[i] = max(local_vc[i], incoming_vc[i])
        local_vc[self.svc_idx] += 1

    def DetectFraud(self, orderId, context):
        logger.debug("Received request %s", orderId)

        if orderId not in self.orders:
            return fraud_detection.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )

        order = self.orders[orderId]

        response = fraud_detection.FraudResponse()
        if order.creditCard.number == '1234123412341234':
            response.is_fraud = True
            response.message = "Order is fraud."
        else:
            response.is_fraud = False # this is not fraud
            response.message = "Order is not a fraud."

        logger.debug("Returning response %s", response)
        return response

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