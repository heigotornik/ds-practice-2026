from dataclasses import dataclass
import logging
import threading
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
add_path('../../../utils/service')

import service_base as service


import orchestrator_pb2 as orchestrator
import orchestrator_pb2_grpc as orchestrator_grpc

import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc


logger = logging.getLogger(__name__)



class TransactionServicesBase(service.Subservice):
    def send_vc_to_fraud_detection(self, id):
        with self.state as state:
            vc = state.vc.get(id)

            if vc is None:
                logger.warning("[%s] Cannot send VC update; unknown id", id)
                return

            with grpc.insecure_channel("fraud_detection:50051") as channel:
                stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)
                request = fraud_detection.StatusUpdateRequest(
                    id=id,
                    TransactionServiceA=vc[0],
                    TransactionServiceB=vc[1],
                    FraudDetection=vc[2],
                    Suggestions=vc[3]
                )
                try:
                    resp = stub.UpdateStatus(request)
                    logger.debug("[%s] Sent VC update to fraud detection", id)
                    if not resp.ok:
                        logger.exception("[%s] Failed to send VC update to fraud detection", id)
                        self._notify_orchestrator_failure(id, resp.message)
                except grpc.RpcError as e:
                    logger.exception("[%s] Failed to send VC update to fraud detection", id)
                    self._notify_orchestrator_failure(id, str(e))
