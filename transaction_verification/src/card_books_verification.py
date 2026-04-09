import logging
from logging.config import dictConfig
import os
import re
import sys

from subservice import Subservice

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

class CardBookVerificationProcess(Subservice):
    def get_service_events(self):
        return {
            (3,0,0,0): self.event_with_cleanup(self.cleanup),
            (2,0,0,0): self.event_with_cleanup(self._send_status_update),
            (1,0,0,0): self.event_with_cleanup(self._verify_credit_card_async),
            (0,0,0,0): self.event_with_cleanup(self._verify_books_async),
        }
    
    def update_vector_clock(self, id):
        with self.condition:
            self.vc[id] = (self.vc[id][0] + 1, self.vc[id][1], self.vc[id][2], self.vc[id][3])
            logger.debug("[%s] Updating vector clock to %s", id, str(self.vc[id]))
            self.condition.notify()
    
    def _send_status_update(self, id):
        logger.debug("[%s] Sending status update to FraudDetection service from CardBookVerification", id)
        self.send_vc_to_fraud_detection(id)
        self.update_vector_clock(id)

    def _verify_credit_card_async(self, id):
        if id not in self.orders:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )
        
        order = self.orders[id]
        logger.debug("[%s] Order data exists", id)
        logger.debug("[%s] Running credit card verification")
        # ---- Credit card verification ----
        cc = order.creditCard
        cc_number = re.sub(r"[\s-]", "", cc.number)

        if not cc_number.isdigit() or len(cc_number) < 13 or len(cc_number) > 19:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Credit card number format is invalid"
            )

        if not re.match(r"^(0[1-9]|1[0-2])\/\d{2}$", cc.expirationDate):
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Expiration date must be in MM/YY format"
            )

        if not cc.cvv.isdigit() or len(cc.cvv) not in (3, 4):
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="CVV must be 3 or 4 digits"
            )
        self.update_vector_clock(id)


    def _verify_books_async(self, id):
        logger.debug("Received request in VerifyBooks: %s", id)

        if id not in self.orders:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )
        
        order = self.orders[id]
        logger.debug("Order data for transaction %s exists", id)

        logger.debug("Running items verification")
        # ---- Items verification ----
        if len(order.items) == 0:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="At least one item must be included"
            )

        for item in order.items:
            if not item.name.strip():
                return transaction_verification.VerifyResponse(
                    isValid=False,
                    message="Each item must have a name"
                )

            if item.quantity <= 0:
                return transaction_verification.VerifyResponse(
                    isValid=False,
                    message=f"Invalid quantity for item '{item.name}'"
                )
        self.update_vector_clock(id)
    
    
