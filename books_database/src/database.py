
import logging
from logging.config import dictConfig
import os
import sys


FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
def add_proto_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)

add_proto_path('../../../utils/pb/books_database')

import books_database_pb2 as books_database
import books_database_pb2_grpc as books_database_grpc


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

class BooksDatabaseService(books_database_grpc.BooksDatabaseServicer):
    def __init__(self):
        self.store = {}


    def Read(self, request, context):
        logger.info("Received read request")
        stock = self.store.get(request.title, 0)
        return books_database.ReadResponse(stock=stock)

    def Write(self, request, context):
        logger.info("Received write request")
        self.store[request.title] = request.new_stock
        return books_database.WriteResponse(success=True)



class PrimaryReplica(BooksDatabaseService):
    def __init__(self, backup_stubs):
        super().__init__()
        self.backup = backup_stubs

    def Write(self, request, context):
        self.store[request.title] = request.new_stock

        for backup_stub in self.backup:
            try:
                backup_stub.Write(request)
            except Exception as e:
                logger.error("Failed to write to backup: %s", e)

        return books_database.WriteResponse(success=True)