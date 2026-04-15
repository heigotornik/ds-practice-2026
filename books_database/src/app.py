import json
import sys
import os
import time

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.


from logging.config import dictConfig
import logging
import threading

import grpc
from concurrent import futures

from database import BooksDatabaseService, PrimaryReplica

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


FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
def add_proto_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)

add_proto_path('../../../utils/pb/books_database')

import books_database_pb2 as books_database
import books_database_pb2_grpc as books_database_grpc



def serve():
    server = grpc.server(futures.ThreadPoolExecutor())

    # Get port and is primary from environment variables, with defaults
    port = int(os.getenv("PORT", 50058))
    is_primary = os.getenv("IS_PRIMARY", "true").lower() == "true"

    # throw if missing
    if port is None:
        logger.error("PORT environment variable is required")
        sys.exit(1)

    if is_primary is None:
        logger.error("IS_PRIMARY environment variable is required")
        sys.exit(1)

    
    # If primary, start the server as primary, otherwise start as backup
    if is_primary:
        logger.info("Starting server as primary")
        # create stubs for other 
        replicas_raw = os.getenv("REPLICAS") # ["database_1:50058", "database_2:50059", "database_3:50060"]
        if replicas_raw is None:
            logger.error("REPLICAS environment variable is required for primary")
            sys.exit(1)
        replicas = json.loads(replicas_raw)
        backup_stubs = []

        # Create a stub for each replica and add it to the list of backup stubs, excluding itself
        for replica in replicas:
            if replica.endswith(f":{port}"):
                continue
            channel = grpc.insecure_channel(replica)
            stub = books_database_grpc.BooksDatabaseServiceStub(channel)
            backup_stubs.append(stub)

        books_database_grpc.add_BooksDatabaseServiceServicer_to_server(
            PrimaryReplica(backup_stubs), server)
    else:
        logger.info("Starting server as backup")
        books_database_grpc.add_BooksDatabaseServiceServicer_to_server(
            BooksDatabaseService(), server)
        
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("Server started. Listening on port %s.", port)
    server.wait_for_termination()

if __name__ == '__main__':
    serve()