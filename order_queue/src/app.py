import json
import sys
import os
import time

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
def add_proto_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)

add_proto_path('../../../utils/pb/order_queue')
add_proto_path('../../../utils/pb/order_executor')

import order_queue_pb2 as order_queue
import order_queue_pb2_grpc as order_queue_grpc

import order_executor_pb2 as order_executor
import order_executor_pb2_grpc as order_executor_grpc

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
    def __init__(self, known_ids):
        self.lock = threading.Lock()
        self.queue = []
        self.known_ids = known_ids # [(id, address)]
        self.accessing_node = None


    def Enqueue(self, request, context):
        result = True 
        with self.lock:
            logger.info("Enqueue request received for id %s", request.id)
            try:
                self.queue.append(request.id)
            except:
                result = False
                logger.error("Failed to enqueue order")
        return order_queue.EnqueueResponse(ok=result)
        

    def Dequeue(self, request, context):
        with self.lock:
            logger.info("Dequeue request received")
            result = None
            try:
                result = self.queue.pop()
            except:
                logger.error("Failed to dequeue order")
                logger.debug("DEV: returning id 1")
                result = 1
        return order_queue.DequeueResponse(id=str(result))
    
    def AccessResource(self, request, context):
        result = True
        with self.lock:
            logger.info("AccessResource request received for node %s", request.nodeId)
            if self.accessing_node is not None and self.accessing_node != request.nodeId:
                result = False
            else:
                self.accessing_node = request.nodeId
                threading.Thread(target=self._check_if_resource_requester_is_alive).start()
        return order_queue.AccessResponse(ok=result)
    
    def _get_accessing_node_address(self):
        if self.accessing_node is None:
            return None
        for id, addr in self.known_ids:
            if id == self.accessing_node:
                return addr
        return None


    def _check_if_resource_requester_is_alive(self):
        while True:
            time.sleep(5)
            with self.lock:
                if self.accessing_node is not None:
                    logger.info("Checking if node %s is alive", self.accessing_node)
                    addr = self._get_accessing_node_address()
                    try:
                        with grpc.insecure_channel(addr) as channel:
                            stub = order_executor_grpc.OrderExecutorServiceStub(channel)
                            request = order_executor.StatusRequest()
                            resp = stub.Status(request)
                            if not resp.isProcessing:
                                logger.warning("Node %s is not processing, releasing resource", self.accessing_node)
                                self.accessing_node = None
                                break
                            logger.info("Node %s is alive and processing", self.accessing_node)
                    except grpc.RpcError:
                        logger.warning("Node %s is not alive, releasing resource", self.accessing_node)
                        self.accessing_node = None
                        break
                else:
                    logger.info("No node is currently accessing the resource stopping")
                    break


def serve():
    # Create a gRPC server
    all_exec_raw = os.getenv("EXECUTORS")
    logger.debug("Raw executors from environment variable: %s", repr(all_exec_raw))
    known_ids = json.loads(all_exec_raw)
    known_ids = [(int(nid), addr) for nid, addr in known_ids]
    logger.debug("Known executors: %s", known_ids)
    server = grpc.server(futures.ThreadPoolExecutor())
    # Add HelloService
    order_queue_grpc.add_OrderQueueServiceServicer_to_server(OrderQueueService(known_ids), server)
    port = "50054"
    server.add_insecure_port("[::]:" + port)
    # Start the server
    server.start()
    logger.info("Server started. Listening on port 50054.")
    # Keep thread alive
    server.wait_for_termination()

if __name__ == '__main__':
    serve()