
import sys
import os

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
suggestion_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestion'))
sys.path.insert(0, suggestion_grpc_path)
import suggestion_pb2 as suggestion
import suggestion_pb2_grpc as suggestion_grpc

import grpc

def suggest(book_id=1234 , book_title="testTitle", book_author="testAuthor"):
    # Establish a connection with the fraud-detection gRPC service.
    with grpc.insecure_channel('suggestions:50053') as channel:
        # Create a stub object.
        stub = suggestion_grpc.SuggestionServiceStub(channel)
        # Call the service through the stub object.
        testBooks = suggestion.BookList(books=[
            suggestion.Book(bookId=1, title="suggestedTitle", author="suggestedAuthor")
        ])
        response = stub.SuggestBooks(testBooks)
    return response.books
