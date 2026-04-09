import sys
import os

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.

# Import Flask.
# Flask is a web framework for Python.
# It allows you to build a web application quickly.
# For more information, see https://flask.palletsprojects.com/en/latest/
from logging.config import dictConfig
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import uuid
import threading
import logging
from concurrent import futures
import grpc

from fraud_api import init_fraud_detection_data
from suggestion_api import init_suggestion_data
from exceptions import FraudulentCheckout, InvalidCheckout
from verification_api import  init_verification_data
from concurrent.futures import ThreadPoolExecutor

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
orchestrator_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/orchestrator'))
sys.path.insert(0, orchestrator_grpc_path)
import orchestrator_pb2 as orchestrator
import orchestrator_pb2_grpc as orchestrator_grpc

order_queue_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/order_queue'))
sys.path.insert(0, order_queue_grpc_path)
import order_queue_pb2 as order_queue
import order_queue_pb2_grpc as order_queue_grpc

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'DEBUG',
        'handlers': ['wsgi']
    }
})


EXECUTOR = ThreadPoolExecutor(max_workers=4)

app = Flask(__name__)
# Enable CORS for the app.
CORS(app, resources={r'/*': {'origins': '*'}})

ORDER_STATE = {}
TOTAL_SERVICES_TO_CHECK = 1  # We only need a "success" message from suggestions service
LOCK = threading.Lock()

class CheckoutResultService(
    orchestrator_grpc.CheckoutResultServiceServicer):

    def ReportResult(self, request, context):
        with LOCK:
            app.logger.info(
                "Received result orderId=%s success=%s message=%s",
                request.orderId,
                request.success,
                request.message
            )
            order = ORDER_STATE.get(request.orderId)
            if not order:
                return orchestrator.Ack(received=False)

            if not request.success:
                order["success"] = False
                order["message"] = request.message
                order["done"].set()
                return orchestrator.Ack(received=True)

            order["responses"] += 1
            if order["responses"] == TOTAL_SERVICES_TO_CHECK:
                order["success"] = True
                order["message"] = request.message
                order["suggested_books"] = request.suggestedBooks
                order["done"].set()
        return orchestrator.Ack(received=True)


@app.errorhandler(InvalidCheckout)
def invalid_api_usage(e):
    return jsonify(e.to_dict()), e.status_code

@app.errorhandler(FraudulentCheckout)
def invalid_api_usage(e):
    return jsonify(e.to_dict()), e.status_code

@app.route('/checkout', methods=['POST'])
def checkout():
    """
    Responds with a JSON object containing the order ID, status, and suggested books.
    """
    # Get request object data to json
    request_data = json.loads(request.data)
    # Print request object data
    app.logger.info("Received checkout: %s", request.data)
    order_id = str(uuid.uuid4())
    init_verification_data(order_id, request_data)
    init_fraud_detection_data(order_id, request_data)
    init_suggestion_data(order_id, request_data)

    ORDER_STATE[order_id] = {
        "success": False,
        "message": "",
        "suggested_books": [],
        "done": threading.Event(),
        "responses": 0
    }
    finished = ORDER_STATE[order_id]["done"].wait(timeout=10)

    if not finished:
        return {"status":"FAILED"},408

    order = ORDER_STATE[order_id]
    if not order["success"]:
        return {
            "orderId":order_id,
            "status":"FAILED",
            "message":order["message"],
            'suggestedBooks': []
        }

    send_order_to_queue(order_id)
    
    return {
        "orderId":order_id,
        "status":"Order Approved",
        'suggestedBooks': [
            {'bookId': order["suggested_books"][0].bookId, 'title': order["suggested_books"][0].title, 'author': order["suggested_books"][0].author},
        ]
    }

def send_order_to_queue(order_id):
    try:
        with grpc.insecure_channel("queue:50054") as channel:
            stub = order_queue_grpc.OrderQueueServiceStub(channel)

            response = stub.Enqueue(
                order_queue.EnqueueRequest(id=order_id)
            )

            if response.ok:
                app.logger.info("Order %s enqueued successfully", order_id)
            else:
                app.logger.error("Failed to enqueue order %s", order_id)

    except grpc.RpcError as e:
        app.logger.error("Queue service unreachable: %s", e)

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

if __name__ == '__main__':
    grpc_thread = threading.Thread(
        target=start_grpc,
        daemon=True
    )
    grpc_thread.start()

    # Run the app in debug mode to enable hot reloading.
    # This is useful for development.
    # The default port is 5000.
    app.run(host='0.0.0.0', threaded=True)
