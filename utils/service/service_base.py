from dataclasses import dataclass
import logging
import os
import sys
import threading
import time
from typing import Any, Callable

import grpc
from opentelemetry.metrics import Observation

from metrics import create_base_service_metrics, get_tracer

FILE = __file__ if "__file__" in globals() else os.getenv("PYTHONFILE", "")


def add_path(relative_path: str):
    abs_path = os.path.abspath(os.path.join(FILE, relative_path))
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)


add_path("../pb/orchestrator")

import orchestrator_pb2 as orchestrator
import orchestrator_pb2_grpc as orchestrator_grpc


logger = logging.getLogger(__name__)


@dataclass
class QueuedTask:
    required_vc: tuple[int, ...]
    action: Callable[[str], Any]


@dataclass
class RunnableEvent:
    id: str
    required_vc: tuple[int, ...]
    action: Callable[[str], Any]


@dataclass
class SubserviceStateView:
    orders: dict[str, Any]
    vc: dict[str, tuple[int, ...]]
    task_queue: dict[str, list[QueuedTask]]
    suggestions: dict[str, Any]


class SubserviceState:
    def __init__(self, condition: threading.Condition):
        self._condition = condition

        self._orders: dict[str, Any] = {}
        self._vc: dict[str, tuple[int, ...]] = {}
        self._task_queue: dict[str, list[QueuedTask]] = {}
        self._suggestions: dict[str, Any] = {}

    def __enter__(self) -> SubserviceStateView:
        self._condition.acquire()

        return SubserviceStateView(
            orders=self._orders,
            vc=self._vc,
            task_queue=self._task_queue,
            suggestions=self._suggestions,
        )

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            self._condition.notify_all()
        finally:
            self._condition.release()

        return False

    def queue_depth(self) -> int:
        self._condition.acquire()
        try:
            return sum(len(queue) for queue in self._task_queue.values())
        finally:
            self._condition.release()


class Subservice:
    def __init__(
        self,
        app_service_name: str | None = None,
        subservice_name: str | None = None,
    ):
        self.app_service_name = (
            app_service_name
            or os.getenv("OTEL_SERVICE_NAME")
            or "unknown-python-service"
        )
        self.subservice_name = subservice_name or self.__class__.__name__

        self.metric_attributes = {
            "app.service": self.app_service_name,
            "subservice": self.subservice_name,
        }

        self.tracer = get_tracer(self.__class__.__module__)

        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.state = SubserviceState(self.condition)

        self.metrics = create_base_service_metrics(
            observe_queue_depth=self._observe_queue_depth,
        )

        channel = grpc.insecure_channel("orchestrator:50050")
        self.orchestrator_stub = orchestrator_grpc.CheckoutResultServiceStub(channel)

    def _observe_queue_depth(self, options=None):
        return [
            Observation(
                self.state.queue_depth(),
                self.metric_attributes,
            )
        ]

    def get_service_events(self):
        raise NotImplementedError("service events are not implemented")

    def _build_task_queue(self) -> list[QueuedTask]:
        """
        Build all upcoming tasks for one order.

        Tasks are sorted by required VC so that lower requirements are considered first.
        The runtime check still uses vector-clock comparison, not just ordering.
        """
        return [
            QueuedTask(
                required_vc=required_vc,
                action=action,
            )
            for required_vc, action in sorted(
                self.get_service_events().items(),
                key=lambda item: item[0],
            )
        ]

    def _runnable_event_with_cleanup(self, fn, id):
        action_name = getattr(fn, "__name__", repr(fn))

        attrs = {
            **self.metric_attributes,
            "operation": action_name,
        }

        event_result = "unknown"

        with self.tracer.start_as_current_span(
            f"{self.subservice_name}.{action_name}"
        ) as span:
            span.set_attribute("app.service", self.app_service_name)
            span.set_attribute("subservice", self.subservice_name)
            span.set_attribute("operation", action_name)
            span.set_attribute("order.id", id)

            started_at = time.perf_counter()

            try:
                logger.debug("[%s] Running event with internal cleanup", id)

                verify_response = fn(id)

                logger.debug("[%s] Event with cleanup FINISHED", id)

                if verify_response is not None and not verify_response.isValid:
                    event_result = "validation_failed"

                    span.set_attribute("validation.valid", False)
                    span.set_attribute("validation.message", verify_response.message)
                    span.set_attribute("event.result", event_result)

                    self.metrics.events_total.add(
                        1,
                        {
                            **attrs,
                            "event.result": event_result,
                        },
                    )

                    logger.error(
                        "[%s] Request is not valid: %s",
                        id,
                        verify_response.message,
                    )

                    self.cleanup(id)

                    self._notify_orchestrator_failure(
                        id,
                        verify_response.message,
                    )
                    return

                event_result = "success"

                span.set_attribute("validation.valid", True)
                span.set_attribute("event.result", event_result)

                self.metrics.events_total.add(
                    1,
                    {
                        **attrs,
                        "event.result": event_result,
                    },
                )

            except Exception as e:
                event_result = "exception"

                span.record_exception(e)
                span.set_attribute("error", True)
                span.set_attribute("event.result", event_result)
                span.set_attribute("exception.type", type(e).__name__)

                self.metrics.events_total.add(
                    1,
                    {
                        **attrs,
                        "event.result": event_result,
                    },
                )

                logger.exception("[%s] Task failed", id)

                self.cleanup(id)

                self._notify_orchestrator_failure(
                    id,
                    str(e),
                )

            finally:
                duration_ms = (time.perf_counter() - started_at) * 1000

                self.metrics.event_duration_ms.record(
                    duration_ms,
                    {
                        **attrs,
                        "event.result": event_result,
                    },
                )

    def _notify_orchestrator_failure(self, order_id, message):
        logger.info(
            "[%s] Notifying orchestrator about failure: %s",
            order_id,
            message,
        )

        request = orchestrator.CheckoutResult(
            orderId=order_id,
            success=False,
            message=message,
        )

        try:
            self.orchestrator_stub.ReportResult(request)
        except grpc.RpcError:
            logger.exception("[%s] Failed to notify orchestrator", order_id)

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

    def event_with_cleanup(self, fn):
        return lambda ident: self._runnable_event_with_cleanup(fn, ident)

    def initialize_order(self, id, order):
        logger.debug("[%s] Received order init", id)

        with self.state as state:
            logger.debug("[%s] Initializing order", id)

            state.vc[id] = (0, 0, 0, 0)
            state.orders[id] = order
            state.task_queue[id] = self._build_task_queue()

            logger.debug(
                "[%s] Created task queue with %d tasks",
                id,
                len(state.task_queue[id]),
            )

    def update_vector_clock(self, id):
        raise NotImplementedError("vector clock update is not implemented")

    def cleanup(self, id):
        with self.state as state:
            logger.debug(
                "[%s] Applying cleanup in service %s",
                id,
                self.__class__.__name__,
            )

            state.orders.pop(id, None)
            state.vc.pop(id, None)
            state.task_queue.pop(id, None)
            state.suggestions.pop(id, None)

    def has_events_to_run(self) -> bool:
        """
        Non-destructive check.

        Use this in condition.wait_for(...). Do not use get_events_to_run()
        inside wait_for because get_events_to_run() pops tasks.
        """
        with self.state as state:
            for order_id, queue in state.task_queue.items():
                current_vc = state.vc.get(order_id)

                if current_vc is None:
                    continue

                if self._find_runnable_task_index(current_vc, queue) is not None:
                    return True

            return False

    def get_events_to_run(self) -> list[RunnableEvent]:
        with self.state as state:
            logger.debug(
                "Getting events to run for service %s",
                self.__class__.__name__,
            )

            events_to_run: list[RunnableEvent] = []

            for order_id in list(state.task_queue):
                current_vc = state.vc.get(order_id)

                if current_vc is None:
                    continue

                queue = state.task_queue.get(order_id, [])

                runnable_index = self._find_runnable_task_index(
                    current_vc,
                    queue,
                )

                if runnable_index is None:
                    continue

                queued_task = queue.pop(runnable_index)

                logger.debug(
                    "[%s] Popped runnable task required_vc=%s",
                    order_id,
                    queued_task.required_vc,
                )

                events_to_run.append(
                    RunnableEvent(
                        id=order_id,
                        required_vc=queued_task.required_vc,
                        action=queued_task.action,
                    )
                )

            logger.debug("Found %d events", len(events_to_run))

            return events_to_run

    def _find_runnable_task_index(
        self,
        current_vc: tuple[int, ...],
        queue: list[QueuedTask],
    ) -> int | None:
        for index, queued_task in enumerate(queue):
            if self._vc_satisfies(current_vc, queued_task.required_vc):
                return index

        return None

    def _vc_satisfies(
        self,
        current_vc: tuple[int, ...],
        required_vc: tuple[int, ...],
    ) -> bool:
        if len(current_vc) != len(required_vc):
            raise ValueError(
                f"VC length mismatch: current={current_vc}, required={required_vc}"
            )

        return all(
            current >= required
            for current, required in zip(current_vc, required_vc)
        )

    def update_with_incoming_vector_clock(self, id, incoming_vc):
        with self.state as state:
            if id not in state.vc:
                logger.warning("[%s] VC update for unknown id, initializing", id)
                state.vc[id] = incoming_vc
                return

            current = state.vc[id]

            if len(current) != len(incoming_vc):
                raise ValueError(
                    f"VC length mismatch: local={current}, incoming={incoming_vc}"
                )

            merged = tuple(
                max(current[i], incoming_vc[i])
                for i in range(len(current))
            )

            logger.debug(
                "[%s] Merging VC: local=%s incoming=%s -> merged=%s",
                id,
                current,
                incoming_vc,
                merged,
            )

            state.vc[id] = merged