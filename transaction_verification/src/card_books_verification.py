import logging
from logging.config import dictConfig
import os
import re
import sys

from subservice import TransactionServicesBase

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

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

class CardBookVerificationProcess(TransactionServicesBase):
    def __init__(self, app_service_name: str = "transaction-verification-service"):
        super().__init__(
            app_service_name=app_service_name,
            subservice_name="card-books-verification",
        )

    def get_service_events(self):
        return {
            (3, 0, 0, 0): self.event_with_cleanup(self.cleanup),
            (2, 0, 0, 0): self.event_with_cleanup(self._send_status_update),
            (1, 0, 0, 0): self.event_with_cleanup(self._verify_credit_card_async),
            (0, 0, 0, 0): self.event_with_cleanup(self._verify_books_async),
        }

    def update_vector_clock(self, id):
        with self.state as state:
            if id not in state.vc:
                raise KeyError(f"Cannot update vector clock for unknown id {id}")

            current = state.vc[id]
            state.vc[id] = (
                current[0] + 1,
                current[1],
                current[2],
                current[3],
            )

            logger.debug("[%s] Updating vector clock to %s", id, str(state.vc[id]))

    def _send_status_update(self, id):
        logger.debug(
            "[%s] Sending status update to FraudDetection service from CardBookVerification",
            id,
        )

        self.update_vector_clock(id)
        self.send_vc_to_fraud_detection(id)

    def _verify_credit_card_async(self, id):
        with self.state as state:
            order = state.orders.get(id)

        if order is None:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first.",
            )

        logger.debug("[%s] Order data exists", id)
        logger.debug("[%s] Running credit card verification", id)

        cc = order.creditCard
        cc_number = re.sub(r"[\s-]", "", cc.number)

        if not cc_number.isdigit() or len(cc_number) < 13 or len(cc_number) > 19:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Credit card number format is invalid",
            )

        if not re.match(r"^(0[1-9]|1[0-2])\/\d{2}$", cc.expirationDate):
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Expiration date must be in MM/YY format",
            )

        if not cc.cvv.isdigit() or len(cc.cvv) not in (3, 4):
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="CVV must be 3 or 4 digits",
            )

        self.update_vector_clock(id)

    def _verify_books_async(self, id):
        logger.debug("[%s] Received request in VerifyBooks", id)

        with self.state as state:
            order = state.orders.get(id)

        if order is None:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first.",
            )

        logger.debug("[%s] Order data exists", id)
        logger.debug("[%s] Running items verification", id)

        if len(order.items) == 0:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="At least one item must be included",
            )

        for item in order.items:
            if not item.name.strip():
                return transaction_verification.VerifyResponse(
                    isValid=False,
                    message="Each item must have a name",
                )

            if item.quantity <= 0:
                return transaction_verification.VerifyResponse(
                    isValid=False,
                    message=f"Invalid quantity for item '{item.name}'",
                )

        self.update_vector_clock(id)
    
