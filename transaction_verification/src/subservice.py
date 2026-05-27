import logging
import os
import sys

import grpc


FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")


def add_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)


add_path("../../../utils/pb/orchestrator")
add_path("../../../utils/pb/fraud_detection")
add_path("../../../utils/service")

import service_base as service

import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc


logger = logging.getLogger(__name__)


class TransactionServicesBase(service.Subservice):
    def send_vc_to_fraud_detection(self, id):
        attrs = {
            **self.metric_attributes,
            "operation": "send_vc_to_fraud_detection",
            "target.service": "fraud-detection",
            "rpc.method": "UpdateStatus",
        }

        with self.tracer.start_as_current_span(
            f"{self.subservice_name}.send_vc_to_fraud_detection"
        ) as span:
            span.set_attribute("app.service", self.app_service_name)
            span.set_attribute("subservice", self.subservice_name)
            span.set_attribute("operation", "send_vc_to_fraud_detection")
            span.set_attribute("target.service", "fraud-detection")
            span.set_attribute("rpc.method", "UpdateStatus")
            span.set_attribute("order.id", id)

            with self.state as state:
                vc = state.vc.get(id)

                if vc is None:
                    logger.warning("[%s] Cannot send VC update; unknown id", id)

                    span.set_attribute("vc.found", False)
                    span.set_attribute("rpc.result", "not_sent")
                    span.set_attribute("event.result", "vc_missing")

                    return

                span.set_attribute("vc.found", True)
                span.set_attribute("vc.value", str(vc))

            with grpc.insecure_channel("fraud_detection:50051") as channel:
                stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)

                request = fraud_detection.StatusUpdateRequest(
                    id=id,
                    TransactionServiceA=vc[0],
                    TransactionServiceB=vc[1],
                    FraudDetection=vc[2],
                    Suggestions=vc[3],
                )

                try:
                    resp = stub.UpdateStatus(request)

                    logger.debug("[%s] Sent VC update to fraud detection", id)

                    if not resp.ok:
                        span.set_attribute("rpc.result", "failure")
                        span.set_attribute("rpc.response.ok", False)
                        span.set_attribute("rpc.response.message", resp.message)
                        span.set_attribute("event.result", "rpc_response_not_ok")

                        logger.error(
                            "[%s] Failed to send VC update to fraud detection: %s",
                            id,
                            resp.message,
                        )

                        self._notify_orchestrator_failure(id, resp.message)
                        return

                    span.set_attribute("rpc.result", "success")
                    span.set_attribute("rpc.response.ok", True)
                    span.set_attribute("event.result", "success")

                except grpc.RpcError as e:
                    span.record_exception(e)
                    span.set_attribute("error", True)
                    span.set_attribute("rpc.result", "exception")
                    span.set_attribute("event.result", "rpc_exception")
                    span.set_attribute("exception.type", type(e).__name__)

                    logger.exception(
                        "[%s] Failed to send VC update to fraud detection",
                        id,
                    )

                    self._notify_orchestrator_failure(id, str(e))