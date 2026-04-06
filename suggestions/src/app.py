import sys
import os
from logging.config import dictConfig
import logging
import grpc
from concurrent import futures
import threading

from book_suggestion import BookSuggestionProcess
from interceptors import LoggingInterceptor

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
suggestion_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestion'))
sys.path.insert(0, suggestion_grpc_path)
import suggestion_pb2 as suggestion
import suggestion_pb2_grpc as suggestion_grpc
orchestrator_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/orchestrator'))
sys.path.insert(0, orchestrator_grpc_path)
import orchestrator_pb2 as orchestrator
import orchestrator_pb2_grpc as orchestrator_grpc

rpc_executor = futures.ThreadPoolExecutor(max_workers=10)

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
# fraud_detection_pb2_grpc.HelloServiceServicer
background_executor = futures.ThreadPoolExecutor(max_workers=4)
class SuggestionService(suggestion_grpc.SuggestionServiceServicer):

    def __init__(self, svc_idx = 3, total_svcs = 4):
        self.svc_idx = svc_idx
        self.total_svcs = total_svcs
        self._lock = threading.Lock()
        self.orders = {}
        self.orderIds = []
        self.eventClocks = {
            (0, 0, 2, 1) : self.suggestBooks
        }
        background_executor.submit(self.checkClocks)

    def checkClocks(self):
        while True:
            for i in range(len(self.orderIds)):
                clock = tuple(self.orders[self.orderIds[i]]["vc"])
                if clock in self.eventClocks:
                    logger.info(f"Clock matches in suggestion")
                    self.orders[self.orderIds[i]]["vc"][self.svc_idx] += 1
                    background_executor.submit(self.eventClocks[clock], self.orderIds[i])

    def InitOrder(self, request, context):
        logger.info(f"Received InitOrder request for transaction {request.id}")
        self.orders[request.id] = {"data": request.order, "vc": [0] * self.total_svcs}
        self.orderIds.append(request.id)
        return suggestion.InitOrderResponse(ok=True)

    def merge_and_increment(self, local_vc, incoming_vc):
        for i in range(self.total_svcs):
            local_vc[i] = max(local_vc[i], incoming_vc[i])
        local_vc[self.svc_idx] += 1
 
    def UpdateStatus(self, request, context):
        logger.info(
            "Received UpdateStatus request for transaction %s with vc",
            request.id
        )

        incoming_vc = tuple([request.TransactionServiceA, request.TransactionServiceB, 
                            request.FraudDetection,
                            request.Suggestions])

        logger.debug(
            "Merging VC for transaction %s into both services: %s",
            request.id,
            incoming_vc
        )

        self.merge_and_increment(self.orders[request.id]["vc"], incoming_vc)

        return suggestion.StatusUpdateResponse(
            ok=True,
            message="Status updated successfully"
        )

    def suggestBooks(self, orderId):
        logger.info(f"Suggesting books for order {orderId}")
        suggestionList = [
                orchestrator.Book(
                    bookId=123,
                    title="testBook",
                    author="testAuthor"
                )
        ]
        logger.debug("Returning suggestion list %s", suggestionList)
        self.notifyOrchestrator(orderId, suggestionList)
    
    def notifyOrchestrator(self, orderId, suggestedBooks):
        with grpc.insecure_channel('orchestrator:50050') as channel:
            logger.info(f"Notifying orchestrator of suggestions for {orderId}")
            stub = orchestrator_grpc.CheckoutResultServiceStub(channel)

            request = orchestrator.CheckoutResult(
                orderId=orderId,
                success=True,
                message="SUCCESS",
                suggestedBooks=suggestedBooks
            )
            try:
                logger.info("notified orchestrator")
                stub.ReportResult(request)

            except grpc.RpcError:
                logger.exception("Failed to notify orchestrator")


def serve():
    # Create a gRPC server
    server = grpc.server(rpc_executor,
                         interceptors=[LoggingInterceptor()])
    # Add HelloService
    suggestion_grpc.add_SuggestionServiceServicer_to_server(SuggestionService(), server)
    # Listen on port 50051
    port = "50053"
    server.add_insecure_port("[::]:" + port)
    # Start the server
    server.start()
    logger.info("Server started. Listening on port 50053.")
    # Keep thread alive
    server.wait_for_termination()

if __name__ == '__main__':
    serve()