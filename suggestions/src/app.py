import sys
import os

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
suggestion_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestion'))
sys.path.insert(0, suggestion_grpc_path)
import suggestion_pb2 as suggestion
import suggestion_pb2_grpc as suggestion_grpc
from logging.config import dictConfig
import logging

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
class SuggestionService(suggestion_grpc.SuggestionServiceServicer):
    # Create an RPC function to say hello
    def SuggestBooks(self, request, context):
        # Create a HelloResponse object
        logger.debug("Received request %s", request)
        inputBooks = request.books
        suggestionList = suggestion.BookList(
            books=[
                suggestion.Book(
                    bookId=123,
                    title="testBook",
                    author="testAuthor"
                )
            ]
        )
        logger.debug("Returning suggestion list %s", suggestionList)
        return suggestionList

def serve():
    # Create a gRPC server
    server = grpc.server(futures.ThreadPoolExecutor())
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