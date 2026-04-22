import threading
import logging
from logging.config import dictConfig
from concurrent import futures
import os
import sys
import grpc

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
def add_proto_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)

add_proto_path('../../../utils/pb/payment')

import payment_pb2 as payment
import payment_pb2_grpc as payment_grpc

dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        }
    },
    'handlers': {
        'default': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['default']
    }
})

logger = logging.getLogger(__name__)


class PaymentService(payment_grpc.PaymentServiceServicer):
    def __init__(self):
        self.lock = threading.Lock()
        self.transactions = {}  # order_id -> state

    def Prepare(self, request, context):
        order_id = request.order_id

        with self.lock:
            state = self.transactions.get(order_id)

            if state == "COMMITTED":
                logger.warning("[Prepare] already committed order %s", order_id)
                return payment.PrepareResponse(ready=False)

            if state == "ABORTED":
                logger.warning("[Prepare] already aborted order %s", order_id)
                return payment.PrepareResponse(ready=False)

            if state == "PREPARED":
                return payment.PrepareResponse(ready=True)

            # Simulate validation (always succeeds)
            self.transactions[order_id] = "PREPARED"
            logger.info("[Prepare] order %s prepared", order_id)

        return payment.PrepareResponse(ready=True)

    def Commit(self, request, context):
        order_id = request.order_id

        with self.lock:
            state = self.transactions.get(order_id)

            if state == "COMMITTED":
                logger.info("[Commit] already committed for order %s", order_id)
                return payment.CommitResponse(success=True)

            if state != "PREPARED":
                logger.warning("[Commit] invalid state for order %s: %s", order_id, state)
                return payment.CommitResponse(success=False)

            # Simulate payment execution
            logger.info("[Commit] payment committed for order %s", order_id)
            self.transactions[order_id] = "COMMITTED"

        return payment.CommitResponse(success=True)

    def Abort(self, request, context):
        order_id = request.order_id

        with self.lock:
            state = self.transactions.get(order_id)

            if state == "COMMITTED":
                logger.warning("[Abort] cannot abort already committed order %s", order_id)
                return payment.AbortResponse(aborted=False)

            if state == "ABORTED":
                logger.info("[Abort] already aborted for order %s", order_id)
                return payment.AbortResponse(aborted=True)

            logger.info("[Abort] payment aborted for order %s", order_id)
            self.transactions[order_id] = "ABORTED"

        return payment.AbortResponse(aborted=True)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    payment_grpc.add_PaymentServiceServicer_to_server(PaymentService(), server)

    port = "50061"
    server.add_insecure_port(f"[::]:{port}")

    server.start()
    logger.info("PaymentService running on port %s", port)

    server.wait_for_termination()


if __name__ == "__main__":
    serve()
