
import logging
import sys
import os

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
suggestion_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestion'))
sys.path.insert(0, suggestion_grpc_path)
import suggestion_pb2 as suggestion
import suggestion_pb2_grpc as suggestion_grpc

import grpc

logger = logging.getLogger(__name__)

def init_suggestion_data(id, order):
    with grpc.insecure_channel('suggestions:50053') as channel:
        logger.info(f"Initializing suggestion for transaction {id}")
        # Create a stub object.
        stub = suggestion_grpc.VerificationServiceStub(channel)
        # Call the service through the stub object.
        testBooks = suggestion.BookList(
            books = [
                suggestion.Book(
                    bookId=123,
                    title="testBook",
                    author="TestAuthor"
                )
            ]
        )
        response = stub.InitOrder(
                suggestion.InitOrderRequest(
                    id=id,
                    books=testBooks
                ))
    return response.ok

def suggest(order_id=0):
    # Establish a connection with the fraud-detection gRPC service.
    with grpc.insecure_channel('suggestions:50053') as channel:
        logger.debug("Requesting suggestions")
        # Create a stub object.
        stub = suggestion_grpc.SuggestionServiceStub(channel)
        # Call the service through the stub object.
        response = stub.SuggestBooks(order_id)
    return response.books
