import logging
from logging.config import dictConfig
import os
import sys

from subservice import TransactionServicesBase

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
transaction_verification_grpc_path = os.path.abspath(
    os.path.join(FILE, '../../../utils/pb/transaction_verification')
)
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
            'stream': sys.stderr,
            'formatter': 'default',
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['grpc']
    }
})


logger = logging.getLogger(__name__)


class UserVerificationProcess(TransactionServicesBase):
    def get_service_events(self):
        return {
            (0, 2, 0, 0): self.event_with_cleanup(self.cleanup),
            (0, 1, 0, 0): self.event_with_cleanup(self._send_status_update),
            (0, 0, 0, 0): self.event_with_cleanup(self._verify_user_data_async),
        }

    def update_vector_clock(self, id):
        with self.state as state:
            if id not in state.vc:
                raise KeyError(f"Cannot update vector clock for unknown id {id}")

            current = state.vc[id]
            state.vc[id] = (
                current[0],
                current[1] + 1,
                current[2],
                current[3],
            )

            logger.debug("[%s] Updating vector clock to %s", id, str(state.vc[id]))

    def _send_status_update(self, id):
        logger.debug(
            "[%s] Sending status update to FraudDetection service from UserVerification",
            id,
        )

        self.update_vector_clock(id)
        self.send_vc_to_fraud_detection(id)

    def _verify_user_data_async(self, id):
        with self.state as state:
            order = state.orders.get(id)

        if order is None:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first.",
            )

        logger.debug("[%s] Order data exists", id)

        logger.debug("[%s] Running user verification", id)

        if not order.user.name.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="User name is required",
            )

        if not order.user.contact.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="User contact is required",
            )

        logger.debug("[%s] Running terms verification", id)

        if not order.termsAccepted:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Terms and conditions must be accepted",
            )

        logger.debug("[%s] Running billing address verification", id)

        addr = order.billingAddress

        if not addr.street.strip() or not addr.city.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Billing address street and city are required",
            )

        if not addr.country.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Billing address country is required",
            )

        logger.info("[%s] All verification checks successful", id)

        self.update_vector_clock(id)

        return transaction_verification.VerifyResponse(
            isValid=True,
            message="Checkout request verified successfully",
        )