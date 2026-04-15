import json
import sys
import os
import time

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
def add_proto_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)

add_proto_path('../../../utils/pb/order_executor')
add_proto_path('../../../utils/pb/order_queue')
add_proto_path('../../../utils/pb/books_database')

import books_database_pb2 as books_database
import books_database_pb2_grpc as books_database_grpc

import order_executor_pb2 as order_executor
import order_executor_pb2_grpc as order_executor_grpc

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



class ExecutorService(order_executor_grpc.OrderExecutorServiceServicer):
    def __init__(self, executor_id, known_ids, queue_stub):
        self.executor_id = executor_id

        self.known_ids = known_ids # [(id, address)]
        self.queue_stub = queue_stub
        
        self.lock = threading.RLock()
        self.leader_id = None
        self.election_in_progress = False

        self.processing_lock = threading.RLock()
        self.processing_order = False
        
    def start_leader_election(self):
        with self.lock:
            if not self.election_in_progress:
                logger.info("Starting leader election")
                self.election_in_progress = True
                self.leader_id = None
                threading.Thread(target=self._leader_election).start()
            
        
    def _leader_election(self):
        higher_nodes = [
            (nid, addr) for nid, addr in self.known_ids
            if nid > self.executor_id
        ]

        logger.debug("Higher nodes to contact during election: %s", higher_nodes)

        while True:
            got_response = False

            for nid, addr in higher_nodes:
                try:
                    with grpc.insecure_channel(addr) as channel:
                        stub = order_executor_grpc.OrderExecutorServiceStub(channel)
                        resp = stub.Election(
                            order_executor.ElectionRequest(node_id=self.executor_id),
                        )
                        if resp.ok:
                            got_response = True
                except grpc.RpcError:
                    logger.debug("Failed to contact higher node %s during election. It might be down.", nid)
                    # node might be down
                    continue

            if not got_response:
                self._become_leader()
            else:
                logger.debug("Got response from higher node during election, waiting for coordinator message")
                time.sleep(10)
            
            with self.lock:
                if not self.election_in_progress:
                    logger.debug("Election already concluded, stopping election thread")
                    break
    
    def _become_leader(self):
        logger.info("Becoming leader with ID %d", self.executor_id)
        with self.lock:
            self.leader_id = self.executor_id
            self.election_in_progress = False

        for nid, addr in self.known_ids:
            if nid != self.executor_id:
                try:
                    with grpc.insecure_channel(addr) as channel:
                        stub = order_executor_grpc.OrderExecutorServiceStub(channel)
                        stub.Coordinator(
                            order_executor.CoordinatorRequest(leader_id=self.executor_id),
                        )
                except grpc.RpcError:
                    logger.debug("Channel %s", addr)
                    logger.debug("Failed to notify node %d  about new leader. It might be down.", nid)
                    # node might be down, but this node is the leader anyway
                    continue
    

    def execute_order(self, title="Some Book", quantity=1):
        with grpc.insecure_channel("books_database:50058") as channel:
            try: 
                    
                response = books_database_grpc.BooksDatabaseStub(channel).Read(
                    books_database.ReadRequest(title=title))
                
                current_stock = response.stock
                if current_stock >= quantity:
                    new_stock = current_stock - quantity
                    write_resp = books_database_grpc.BooksDatabaseStub(channel).Write(
                        books_database.WriteRequest(title=title, new_stock=new_stock))
                    logger.info("Executed order for %d of %s. New stock: %d", quantity, title, new_stock)
                    return write_resp.success
            except grpc.RpcError as e:
                logger.error("Failed to contact books database service: %s", e)
                return False
        logger.warning("Not enough stock to execute order for %d of %s. Current stock: %d", quantity, title, current_stock)
        return False
            

    def process_orders(self):
        logger.debug("Processing orders as leader")
        with grpc.insecure_channel("queue:50054") as channel:
            try:
                order_id = self.queue_stub(channel).Dequeue(order_queue.DequeueRequest(dummy=str(1)))

                if order_id is not None:
                    logger.info("Processing order %s", order_id)
                    with self.processing_lock:
                        self.processing_order = True
                    self.execute_order()
                    logger.info("Finished processing order %s", order_id)
                    with self.processing_lock:
                        self.processing_order = False
                else:
                    logger.debug("No orders to process")
            except grpc.RpcError as e:
                logger.error("Failed to contact order queue service: %s", e)

    def _get_leader_address(self):
        with self.lock:
            leader_id = self.leader_id
        for nid, addr in self.known_ids:
            if nid == leader_id:
                return addr
        return None

    def _send_heartbeat(self):
        leader_addr = self._get_leader_address()
        if leader_addr is None:
            logger.warning("No leader address found. Cannot send heartbeat.")
            return
        with grpc.insecure_channel(leader_addr) as channel:
            stub = order_executor_grpc.OrderExecutorServiceStub(channel)
            stub.Heartbeat(order_executor.HeartbeatRequest(requesting_node=self.executor_id))

    def run(self):
        while True:
            
            if self.leader_id == self.executor_id:
                logger.debug("Node %s is the leader, processing orders", self.leader_id)
                with self.processing_lock:
                    if self.processing_order:
                        logger.debug("Already processing an order, skipping this cycle")
                        continue
                    with grpc.insecure_channel("queue:50054") as channel:
                        stub = order_queue_grpc.OrderQueueServiceStub(channel)
                        try:
                            resp = stub.AccessResource(order_queue.AccessRequest(nodeId=self.executor_id))
                            if resp.ok:
                                self.process_orders()
                            else:
                                logger.warning("Access to order queue denied by resource manager even as leader. Message: %s")
                        except grpc.RpcError as e:
                            logger.error("Failed to access order queue service: %s", e)
                            
            elif self.leader_id is not None:
                try:
                    self._send_heartbeat()
                except grpc.RpcError:
                    logger.warning("Failed to contact leader %s. It might be down. Starting new election.", self.leader_id)
                    self.start_leader_election()
            else:
                logger.debug("No leader currently elected. Starting election.")
                self.start_leader_election()

            if self.leader_id != self.executor_id:
                logger.info("Waiting to check leadership")
                time.sleep(10)
            else:
                logger.debug("Currently the leader, dequeuing soon")
                time.sleep(1)

    def Election(self, request, context):
        logger.info("Received election message from node %d", request.node_id)
        incoming_id = request.node_id

        if incoming_id < self.executor_id:
            logger.info("Node %d has lower ID than self (%d). Responding OK and starting election.", incoming_id, self.executor_id)
            self.start_leader_election()
            return order_executor.ElectionResponse(ok=True)
        return order_executor.ElectionResponse(ok=False)

    def Coordinator(self, request, context):
        logger.info("Coordinator Message received. Node %d is the new leader", request.leader_id)
        with self.lock:
            self.leader_id = request.leader_id
            self.election_in_progress = False
        return order_executor.CoordinatorResponse(acknowledged=True)

    def Heartbeat(self, request, context):
        logger.info("Received heartbeat from node %d", request.requesting_node)
        return order_executor.HeartbeatResponse(responding_node=self.executor_id)

    def Status(self, request, context):
        logger.info("Received status request")
        processing = self.processing_order
        logger.info("Status request: currently isProcessing : %s", processing)
        return order_executor.StatusResponse(
            isProcessing=processing)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    all_exec_raw = os.getenv("EXECUTORS")
    known_ids = json.loads(all_exec_raw)
    known_ids = [(int(nid), addr) for nid, addr in known_ids]
    logger.debug("Known executors: %s", known_ids)
    exec_id = os.getenv("EXECUTOR_ID")
    port = os.getenv("PORT")


    if known_ids is None or exec_id is None:
        raise RuntimeError("Environment variables 'EXECUTORS' and 'EXECUTOR_ID' must be set")

    exec_service = ExecutorService(
            executor_id=int(exec_id),
            known_ids=known_ids,
            queue_stub=order_queue_grpc.OrderQueueServiceStub
        )

    order_executor_grpc.add_OrderExecutorServiceServicer_to_server(
        exec_service, server)

    server.add_insecure_port("[::]:" + port)
    server.start()
    logger.info("Server started. Listening on port %s.", port)

    threading.Thread(target=exec_service.run).start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()