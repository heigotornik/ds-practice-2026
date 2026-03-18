import os
import sys
import grpc
import logging
from concurrent import futures

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
orchestrator_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/orchestrator'))
sys.path.insert(0, orchestrator_grpc_path)
import orchestrator_pb2 as orchestrator
import orchestrator_pb2_grpc as orchestrator_grpc

class CheckoutResultService(
    orchestrator_grpc.CheckoutResultServiceServicer):

    def ReportResult(self, request, context):
        from app import update_order

        update_order(
            request.orderId,
            request.success,
            request.message
            # TODO: should be suggestions here probably?
        )
        return orchestrator.Ack(received=True)

def start_grpc():
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10)
    )
    orchestrator_grpc.add_CheckoutResultServiceServicer_to_server(
        CheckoutResultService(),
        server
    )

    server.add_insecure_port('[::]:50050')
    server.start()
    logging.info("Server started. Listening on port 50050")
    server.wait_for_termination()

