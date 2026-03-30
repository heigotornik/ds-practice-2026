

from dataclasses import dataclass
import logging
import threading
logger = logging.getLogger(__name__)


@dataclass
class RunnableEvent:
    id: str
    action: callable

class Subservice:
    def __init__(self):
        self.orders = {}
        self.vc = {}
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        
    def get_service_events(self):
        raise NotImplementedError("service events are not implemented")

    def update_condition(self):
        logger.debug("Updating condition for %s", self.__class__.__name__)
        with self.condition:
            self.condition.notify_all()

    def get_condition(self):
        return self.condition
    
    def create_new_vector_clock_entry(self, id):
        self.vc[id] = (0,0,0,0)

    def initialize_order(self, id, order):
        with self.condition:
            logger.debug("Initializing order with id %s", id)
            self.create_new_vector_clock_entry(id)
            self.orders[id] = order
            self.condition.notify_all()
    
    def update_vector_clock(self, id):
        raise NotImplementedError("vector clock update is not implemented")
    
    def cleanup(self, id):
        with self.lock:
            self.orders.pop(id, None)
            self.vc.pop(id, None)

    def get_events_to_run(self):
        with self.lock:
            logger.debug("Getting events to run for %s", self.__class__.__name__)
            events_to_run = []
            for id in list(self.orders):  # snapshot optional but safer
                event = self.get_event(id)
                if event is not None:
                    events_to_run.append(RunnableEvent(id, event))
            logger.debug("Found %d events", len(events_to_run))
            return events_to_run

    def get_event(self, id):
        for event_vc, action in self.get_service_events().items():
            if all(self.vc[id][i] >= event_vc[i] for i in range(len(self.vc[id]))):
                return action
        return None
