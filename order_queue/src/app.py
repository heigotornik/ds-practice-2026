import sys
import os

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
order_queue_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/order_queue'))
sys.path.insert(0, order_queue_grpc_path)
import order_queue_pb2 as order_queue
import order_queue_pb2_grpc as order_queue_grpc
from logging.config import dictConfig
import logging
import threading

import grpc
from concurrent import futures

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
class OrderQueueService(order_queue_grpc.OrderQueueServiceServicer):
    def __init__(self):
        self.lock = threading.Lock()
        self.queue = []

    def Enqueue(self, request, context):
        result = True 
        with self.lock:
            try:
                self.queue.append(request.id)
            except:
                result = False
                logger.error("Failed to enqueue order")
        return order_queue.EnqueueResponse(ok=result)
        

    def Dequeue(self, request, context):
        with self.lock:
            result = None
            try:
                result = self.queue.pop()
            except:
                logger.error("Failed to dequeue order")
                logger.debug("DEV: returning id 1")
                result = 1
        return order_queue.DequeueResponse(id=result)


def serve():
    # Create a gRPC server
    server = grpc.server(futures.ThreadPoolExecutor())
    # Add HelloService
    order_queue_grpc.add_OrderQueueServiceServicer_to_server(OrderQueueService(), server)
    # Listen on port 50051
    port = "50054"
    server.add_insecure_port("[::]:" + port)
    # Start the server
    server.start()
    logger.info("Server started. Listening on port 50054.")
    # Keep thread alive
    server.wait_for_termination()

if __name__ == '__main__':
    serve()