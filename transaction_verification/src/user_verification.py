import logging
from logging.config import dictConfig
import os
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

class UserVerificationProcess(Subservice):
    def get_service_events(self):
        return {
            (0,2,0,0): self.event_with_cleanup(self.cleanup),
            (0,1,0,0): self.event_with_cleanup(self._send_status_update),
            (0,0,0,0): self.event_with_cleanup(self._verify_user_data_async),
        }
    
    def update_vector_clock(self, id):
        with self.condition:
            self.vc[id] = (self.vc[id][0], self.vc[id][1]+1, self.vc[id][2], self.vc[id][3])
            logger.debug("[%s] Updating vector clock to %s", id, str(self.vc[id]))
            self.condition.notify()

    def _send_status_update(self, id):
        logger.debug("[%s] Sending status update to FraudDetection service from UserVerification", id)
        self.update_vector_clock(id)
        self.send_vc_to_fraud_detection(id)
    
    def _verify_user_data_async(self, id):

        if id not in self.orders:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )
        
        order = self.orders[id]
        logger.debug("Order data for transaction %s exists", id)

        # ---- User verification ----
        logger.debug("Running user verification")
        if not order.user.name.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="User name is required"
            )

        if not order.user.contact.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="User contact is required"
            )

        logger.debug("Running terms verification")
        # ---- Terms verification ----
        if not order.termsAccepted:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Terms and conditions must be accepted"
            )

        logger.debug("Running billing address verification")
        # ---- Billing address verification ----
        addr = order.billingAddress
        if not addr.street.strip() or not addr.city.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Billing address street and city are required"
            )

        if not addr.country.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Billing address country is required"
            )

        # ---- Success ----
        logger.info("All verification checks successful for order ID %s", id)
        self.update_vector_clock(id)

        return transaction_verification.VerifyResponse(
            isValid=True,
            message="Checkout request verified successfully"
        )


    
