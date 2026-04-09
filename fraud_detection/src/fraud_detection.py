import logging
from logging.config import dictConfig
import os
import sys

from subservice import Subservice

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection 
import fraud_detection_pb2_grpc as fraud_detection_grpc

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

class FraudDetectionProcess(Subservice):
    def get_service_events(self):
        return {
            (3,2,3,0): self.event_with_cleanup(self.cleanup),
            (3,2,2,0): self.event_with_cleanup(self._send_status_update),
            (3,2,1,0): self.event_with_cleanup(self._check_credit_card),
            (2,0,0,0): self.event_with_cleanup(self._check_user_data),
        }
    
    def update_vector_clock(self, id):
        with self.condition:
            self.vc[id] = (self.vc[id][0], self.vc[id][1], self.vc[id][2]+1, self.vc[id][3])
            logger.debug("Updating vector clock for %s to %s", id, str(self.vc[id]))
            self.condition.notify()

    def _send_status_update(self, id):
        logger.debug("Sending status update to orchestrator")


        self.update_vector_clock(id)
        self.send_vc_to_suggestion(id)
    
    def _check_user_data(self, id):
        if id not in self.orders:
            return fraud_detection.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )

        order = self.orders[id]

        if order.user.name == 'Fraudster':
            return fraud_detection.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )
        self.update_vector_clock(id)

    def _check_credit_card(self, id):
        if id not in self.orders:
            return fraud_detection.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )

        order = self.orders[id]

        if order.creditCard.number == '1234123412341234':
            return fraud_detection.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )
        self.update_vector_clock(id)