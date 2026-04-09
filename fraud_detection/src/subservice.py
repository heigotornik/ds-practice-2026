from dataclasses import dataclass
import logging
import threading
import os
import sys
import grpc


FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
def add_proto_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)

add_proto_path('../../../utils/pb/suggestion')
add_proto_path('../../../utils/pb/orchestrator')
add_proto_path('../../../utils/pb/fraud_detection')


import orchestrator_pb2 as orchestrator
import orchestrator_pb2_grpc as orchestrator_grpc

import suggestion_pb2 as suggestion
import suggestion_pb2_grpc as suggestion_grpc


logger = logging.getLogger(__name__)




@dataclass
class RunnableEvent:
    id: str
    action: callable

class Subservice:
    def __init__(self):
        self.orders = {}
        self.suggestions = {}

        # VC updating
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.vc = {}
        # ID to events
        # no multiple tasks running with same ID supported 
        self.tasks_running = set()

        # Create connection to orchestrator
        channel = grpc.insecure_channel("orchestrator:50050")
        self.orchestrator_stub = orchestrator_grpc.CheckoutResultServiceStub(channel)
        
    def get_service_events(self):
        raise NotImplementedError("service events are not implemented")
    
    def send_vc_to_suggestion(self, id):
        with self.lock:
            with grpc.insecure_channel("suggestions:50053") as channel:
                stub = suggestion_grpc.SuggestionServiceStub(channel)
                request = suggestion.StatusUpdateRequest(
                    id=id,
                    TransactionServiceA=self.vc[id][0],
                    TransactionServiceB=self.vc[id][1],
                    FraudDetection=self.vc[id][2],
                    Suggestions=self.vc[id][3]
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

    def _runnable_event_with_cleanup(self, fn, id):
        try:
            logger.debug("Running event with cleanup for %s", id)
            verify_response = fn(id)
            logger.debug("Event with cleanup for %s FINISHED", id)

            if verify_response is not None and not verify_response.isValid:
                logger.error("Request is not valid %s", id)
                # Clean up in case of errors to avoid looping the same event.
                self.cleanup(id)
                self._notify_orchestrator_failure(
                    id,
                    verify_response.message
                )

        except Exception as e:
            logger.error("Task failed for ID %s. Error: %s", id, e)
            # Clean up in case of errors to avoid looping the same event.
            self.cleanup(id)
            self._notify_orchestrator_failure(
                id,
                str(e)
            )
        finally:
            self.remove_task_running(id)

    def _notify_orchestrator_failure(self, order_id, message):
        logger.info("Notifying orchestrator about failure: %s", message)
        request = orchestrator.CheckoutResult(
            orderId=order_id,
            success=False,
            message=message
        )
        try:
            self.orchestrator_stub.ReportResult(request)

        except grpc.RpcError:
            logger.exception("Failed to notify orchestrator")
   
    def notify_orchestrator_success(self, order_id, suggested_books):
        logger.info("Notifying orchestrator about success.")
        request = orchestrator.CheckoutResult(
            orderId=order_id,
            success=True,
            message="SUCCESS",
            suggestedBooks=suggested_books
        )
        try:
            self.orchestrator_stub.ReportResult(request)

        except grpc.RpcError:
            logger.exception("Failed to notify orchestrator")
    
    def event_with_cleanup(self, fn):
        return lambda ident: self._runnable_event_with_cleanup(fn, ident)


    def add_task_running(self, id):
        with self.condition:
            self.tasks_running.add(id)
            logger.debug("Added task running for %s", id)
            self.condition.notify()
    
    def remove_task_running(self, id):
        with self.condition:
            self.tasks_running.remove(id)
            logger.debug("Removed task running for %s", id)
            self.condition.notify()
    
    def _create_new_vector_clock_entry(self, id):
        self.vc[id] = (0,0,0,0)

    def initialize_order(self, id, order):
        logger.debug("Received order init with id %s", id)
        with self.condition:
            logger.debug("Initializing order with id %s", id)
            logger.debug("Events %s", str(self.tasks_running))
            self._create_new_vector_clock_entry(id)
            self.orders[id] = order
            self.condition.notify()
    
    def update_vector_clock(self, id):
        raise NotImplementedError("vector clock update is not implemented")
    
    def cleanup(self, id):
        with self.lock:
            logger.debug("Applying cleanup for %s, order id %s", self.__class__.__name__, id)
            self.orders.pop(id, None)
            self.suggestions.pop(id, None)
            self.vc.pop(id, None)

    def get_events_to_run(self):
        with self.lock:
            logger.debug("Getting events to run for %s", self.__class__.__name__)
            events_to_run = []
            for id in list(self.orders):
                if id in self.tasks_running:
                    continue
                event = self._get_event(id)
                if event is not None:
                    events_to_run.append(RunnableEvent(id, event))
            logger.debug("Found %d events", len(events_to_run))
            return events_to_run

    def _get_event(self, id):
        for event_vc, action in self.get_service_events().items():
            if all(self.vc[id][i] == event_vc[i] for i in range(len(self.vc[id]))):
                logger.debug("%s", str(self.vc))
                return action
        return None
    
    def update_with_incoming_vector_clock(self, id, incoming_vc):
        with self.lock:
            if id not in self.vc:
                logger.warning("VC update for unknown id %s, initializing", id)
                self.vc[id] = incoming_vc
            else:
                current = self.vc[id]

                if len(current) != len(incoming_vc):
                    raise ValueError(
                        f"VC length mismatch: local={current}, incoming={incoming_vc}"
                    )

                merged = tuple(
                    max(current[i], incoming_vc[i])
                    for i in range(len(current))
                )

                logger.debug(
                    "Merging VC for %s: local=%s incoming=%s -> merged=%s",
                    id,
                    current,
                    incoming_vc,
                    merged
                )

                self.vc[id] = merged