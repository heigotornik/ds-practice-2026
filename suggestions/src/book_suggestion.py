import logging
from logging.config import dictConfig
import os
import sys

from subservice import Subservice

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
suggestion_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestion'))
sys.path.insert(0, suggestion_grpc_path)
import suggestion_pb2 as suggestion
import suggestion_pb2_grpc as suggestion_grpc

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
orchestrator_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/orchestrator'))
sys.path.insert(0, orchestrator_grpc_path)
import orchestrator_pb2 as orchestrator


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

class BookSuggestionProcess(Subservice):
    def get_service_events(self):
        return {
            (3,2,3,2): self.event_with_cleanup(self.cleanup),
            (3,2,3,1): self.event_with_cleanup(self._send_status_update),
            (3,2,3,0): self.event_with_cleanup(self._create_suggestions),
        }
    
    def update_vector_clock(self, id):
        with self.condition:
            self.vc[id] = (self.vc[id][0], self.vc[id][1], self.vc[id][2], self.vc[id][3]+1)
            logger.debug("Updating vector clock for %s to %s", id, str(self.vc[id]))
            self.condition.notify()

    def _send_status_update(self, id):
        logger.debug("Sending status update to orchestrator")

        if id not in self.orders:
            return suggestion.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )

        if self.suggestions[id] is None:
            return suggestion.VerifyResponse(
                isValid=False,
                message="Book suggestions not found. Something went wrong."
            )
        
        self.notify_orchestrator_success(id, self.suggestions[id])
        self.update_vector_clock(id)
    
    def _create_suggestions(self, id):
        logger.debug("Received request id %s", id)

        if id not in self.orders:
            return suggestion.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )
        
        order = self.orders[id]
        logger.debug("Order data for transaction %s exists", id)

        # ---- Create Suggestions ----
        logger.debug(f"Suggesting for order id {id}")
        _input_books = order.items
        self.suggestions[id] = [
            orchestrator.Book(
                bookId=123,
                title="testBook",
                author="testAuthor"
            )
        ]

        # ---- Success ----
        logger.info("Created suggestions list %s", self.suggestions[id])
        self.update_vector_clock(id)

        return suggestion.VerifyResponse(
            isValid=True,
            message="Checkout request verified successfully"
        )
