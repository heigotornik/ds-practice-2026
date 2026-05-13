import logging
from logging.config import dictConfig
import os
import sys
import grpc

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
def add_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)

add_path('../../../utils/pb/orchestrator')
add_path('../../../utils/pb/suggestion')
add_path('../../../utils/service')

import suggestion_pb2 as suggestion
import suggestion_pb2_grpc as suggestion_grpc

import orchestrator_pb2 as orchestrator
import service_base as service

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

class BookSuggestionProcess(service.Subservice):
    def notify_orchestrator_success(self, order_id, suggested_books):
        logger.info("[%s] Notifying orchestrator about success", order_id)

        request = orchestrator.CheckoutResult(
            orderId=order_id,
            success=True,
            message="SUCCESS",
            suggestedBooks=suggested_books,
        )

        try:
            self.orchestrator_stub.ReportResult(request)

        except grpc.RpcError:
            logger.exception("[%s] Failed to notify orchestrator", order_id)

    def get_service_events(self):
        return {
            (3, 2, 5, 2): self.event_with_cleanup(self.cleanup),
            (3, 2, 5, 1): self.event_with_cleanup(self._send_status_update),
            (3, 2, 5, 0): self.event_with_cleanup(self._create_suggestions),
        }

    def update_vector_clock(self, id):
        with self.state as state:
            if id not in state.vc:
                raise KeyError(f"Cannot update vector clock for unknown id {id}")

            current = state.vc[id]
            state.vc[id] = (
                current[0],
                current[1],
                current[2],
                current[3] + 1,
            )

            logger.debug(
                "[%s] Updating vector clock to %s",
                id,
                str(state.vc[id]),
            )

    def _send_status_update(self, id):
        logger.debug("[%s] Sending status update to orchestrator", id)

        with self.state as state:
            order = state.orders.get(id)
            suggested_books = state.suggestions.get(id)

        if order is None:
            return suggestion.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first.",
            )

        if suggested_books is None:
            return suggestion.VerifyResponse(
                isValid=False,
                message="Book suggestions not found. Something went wrong.",
            )

        self.notify_orchestrator_success(id, suggested_books)
        self.update_vector_clock(id)

    def _create_suggestions(self, id):
        logger.info("[%s] Creating book suggestions", id)

        with self.state as state:
            order = state.orders.get(id)

            if order is None:
                return suggestion.VerifyResponse(
                    isValid=False,
                    message="Order ID not found. Please initialize the order first.",
                )

            logger.debug("[%s] Order data exists", id)
            logger.debug("[%s] Suggesting books", id)

            _input_books = order.items

            state.suggestions[id] = [
                orchestrator.Book(
                    bookId=123,
                    title="testBook",
                    author="testAuthor",
                )
            ]

            suggested_books = state.suggestions[id]

        logger.info("[%s] Created suggestions list %s", id, suggested_books)

        self.update_vector_clock(id)

        return suggestion.VerifyResponse(
            isValid=True,
            message="Checkout request verified successfully",
        )