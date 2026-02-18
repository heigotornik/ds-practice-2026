import sys
import os

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
suggestion_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestion'))
sys.path.insert(0, suggestion_grpc_path)
import suggestion_pb2 as suggestion
import suggestion_grpc as suggestion_grpc

import grpc
from concurrent import futures

# Create a class to define the server functions, derived from
# fraud_detection_pb2_grpc.HelloServiceServicer
class SuggestionService(suggestion_grpc.SuggestionServiceServicer):
    # Create an RPC function to say hello
    def SuggestBooks(self, request, context):
        # Create a HelloResponse object
        inputBooks = request.books
        testbook1 = suggestion.Book()
        response = suggestion.BookList( {testbook1} ) 
        # Set the greeting field of the response object
        # Print the greeting message
        # Return the response object
        return response

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
    print("Server started. Listening on port 50051.")
    # Keep thread alive
    server.wait_for_termination()

if __name__ == '__main__':
    serve()