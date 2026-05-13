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
add_path('../../../utils/pb/fraud_detection')
add_path('../../../utils/pb/suggestion')
add_path('../../../utils/service')

import fraud_detection_pb2 as fraud_detection 
import fraud_detection_pb2_grpc as fraud_detection_grpc

import orchestrator_pb2 as orchestrator
import service_base as service

import suggestion_pb2 as suggestion
import suggestion_pb2_grpc as suggestion_grpc


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

class FraudDetectionProcess(service.Subservice):
    def send_vc_to_suggestion(self, id):
        with self.state as state:
            vc = state.vc.get(id)

        if vc is None:
            logger.warning("[%s] Cannot send VC update to suggestion; unknown id", id)
            return

        with grpc.insecure_channel("suggestions:50053") as channel:
            stub = suggestion_grpc.SuggestionServiceStub(channel)

            request = suggestion.StatusUpdateRequest(
                id=id,
                TransactionServiceA=vc[0],
                TransactionServiceB=vc[1],
                FraudDetection=vc[2],
                Suggestions=vc[3],
            )

            try:
                resp = stub.UpdateStatus(request)
                logger.debug("[%s] Sent VC update to suggestion", id)

                if not resp.ok:
                    logger.exception("[%s] Failed to send VC update to suggestion", id)
                    self._notify_orchestrator_failure(id, resp.message)

            except grpc.RpcError as e:
                logger.exception("[%s] Failed to send VC update to suggestion", id)
                self._notify_orchestrator_failure(id, str(e))

    def get_service_events(self):
        return {
            (3, 2, 5, 0): self.event_with_cleanup(self.cleanup),
            (3, 2, 4, 0): self.event_with_cleanup(self._send_status_update),
            (3, 2, 3, 0): self.event_with_cleanup(self._check_credit_card),
            (0, 2, 1, 0): self.event_with_cleanup(self._check_user_data),
        }

    def update_vector_clock(self, id):
        with self.state as state:
            if id not in state.vc:
                raise KeyError(f"Cannot update vector clock for unknown id {id}")

            current = state.vc[id]
            state.vc[id] = (
                current[0],
                current[1],
                current[2] + 1,
                current[3],
            )

            logger.debug(
                "[%s] Updating vector clock to %s",
                id,
                str(state.vc[id]),
            )

    def _send_status_update(self, id):
        logger.debug("[%s] Sending status update to suggestion", id)

        self.update_vector_clock(id)
        self.send_vc_to_suggestion(id)

    def _check_user_data(self, id):
        logger.info("[%s] Checking user data in FraudDetection", id)

        with self.state as state:
            order = state.orders.get(id)

        if order is None:
            return fraud_detection.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first.",
            )

        if order.user.name == "Fraudster":
            return fraud_detection.VerifyResponse(
                isValid=False,
                message="Fraudulent user detected.",
            )

        self.update_vector_clock(id)

    def _check_credit_card(self, id):
        logger.info("[%s] Checking credit card in FraudDetection", id)

        with self.state as state:
            order = state.orders.get(id)

        if order is None:
            return fraud_detection.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first.",
            )

        if order.creditCard.number == "1234123412341234":
            return fraud_detection.VerifyResponse(
                isValid=False,
                message="Fraudulent credit card detected.",
            )

        self.update_vector_clock(id)