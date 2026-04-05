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
# fraud_detection_pb2_grpc.HelloServiceServicer
class SuggestionService(suggestion_grpc.SuggestionServiceServicer):

    def __init__(self):
        self.bookSuggestion = BookSuggestionProcess()
        background_executor.submit(self.worker, self.bookSuggestion)

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
        self.bookSuggestion.initialize_order(request.id, request.order)
        return suggestion.InitOrderResponse(ok=True)
 
    def UpdateStatus(self, request, context):
        logger.info(
            "Received UpdateStatus request for transaction %s with vc=%s",
            request.id,
            request.vc
        )

        if request.id not in self.bookSuggestion.orders:
            return suggestion.UpdateStatusResponse(
                ok=False,
                message="Order ID not found. Please initialize the order first."
            )

        incoming_vc = tuple(request.vc)

        logger.debug(
            "Merging VC for transaction %s into both services: %s",
            request.id,
            incoming_vc
        )

        self.bookSuggestion.update_with_incoming_vector_clock(request.id, incoming_vc)

        return suggestion.UpdateStatusResponse(
            ok=True,
            message="Status updated successfully"
        )

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