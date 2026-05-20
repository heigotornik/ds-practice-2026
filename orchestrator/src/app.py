import sys
import os

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
from verification_api import init_verification_data
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
CORS(app, resources={r'/*': {'origins': '*'}})

ORDER_STATE = {}
TOTAL_SERVICES_TO_CHECK = 1
LOCK = threading.Lock()


class CheckoutResultService(
    orchestrator_grpc.CheckoutResultServiceServicer
):
    def ReportResult(self, request, context):
        with LOCK:
            app.logger.info(
                "[%s] Received result success=%s message=%s",
                request.orderId,
                request.success,
                request.message,
            )

            order = ORDER_STATE.get(request.orderId)

            if not order:
                app.logger.warning(
                    "[%s] Received result for unknown order",
                    request.orderId,
                )
                return orchestrator.Ack(received=False)

            if not request.success:
                app.logger.error(
                    "[%s] Checkout failed: %s",
                    request.orderId,
                    request.message,
                )

                order["success"] = False
                order["message"] = request.message
                order["done"].set()

                return orchestrator.Ack(received=True)

            order["responses"] += 1

            app.logger.debug(
                "[%s] Received successful response %d/%d",
                request.orderId,
                order["responses"],
                TOTAL_SERVICES_TO_CHECK,
            )

            if order["responses"] == TOTAL_SERVICES_TO_CHECK:
                app.logger.info(
                    "[%s] Checkout completed successfully",
                    request.orderId,
                )

                order["success"] = True
                order["message"] = request.message
                order["suggested_books"] = request.suggestedBooks
                order["done"].set()

        return orchestrator.Ack(received=True)


@app.errorhandler(InvalidCheckout)
def invalid_api_usage(e):
    return jsonify(e.to_dict()), e.status_code


@app.errorhandler(FraudulentCheckout)
def fraudulent_checkout(e):
    return jsonify(e.to_dict()), e.status_code


@app.route('/checkout', methods=['POST'])
def checkout():
    """
    Responds with a JSON object containing the order ID, status, and suggested books.
    """
    order_id = str(uuid.uuid4())
    request_data = json.loads(request.data)

    app.logger.info("[%s] Received checkout: %s", order_id, request.data)

    init_suggestion_data(order_id, request_data)
    init_fraud_detection_data(order_id, request_data)
    init_verification_data(order_id, request_data)

    ORDER_STATE[order_id] = {
        "success": False,
        "message": "",
        "suggested_books": [],
        "done": threading.Event(),
        "responses": 0,
    }

    app.logger.debug("[%s] Waiting for checkout result", order_id)

    finished = ORDER_STATE[order_id]["done"].wait(timeout=30)

    if not finished:
        app.logger.warning("[%s] Checkout timed out", order_id)
        return {"status": "FAILED"}, 408

    order = ORDER_STATE[order_id]

    if not order["success"]:
        app.logger.error(
            "[%s] Checkout rejected: %s",
            order_id,
            order["message"],
        )

        return {
            "orderId": order_id,
            "status": "FAILED",
            "message": order["message"],
            "suggestedBooks": [],
        }

    send_order_to_queue(
        order_id,
        request_data["items"][0]["name"],
        request_data["items"][0]["quantity"],
    )

    app.logger.info("[%s] Checkout approved", order_id)

    return {
        "orderId": order_id,
        "status": "Order Approved",
        "suggestedBooks": [
            {
                "bookId": order["suggested_books"][0].bookId,
                "title": order["suggested_books"][0].title,
                "author": order["suggested_books"][0].author,
            },
        ],
    }


def send_order_to_queue(order_id, title, quantity):
    try:
        with grpc.insecure_channel("queue:50054") as channel:
            stub = order_queue_grpc.OrderQueueServiceStub(channel)

            response = stub.Enqueue(
                order_queue.EnqueueRequest(id=order_id, title=title, quantity=quantity)
            )

            if response.ok:
                app.logger.info("[%s] Order enqueued successfully", order_id)
            else:
                app.logger.error("[%s] Failed to enqueue order", order_id)

    except grpc.RpcError:
        app.logger.exception("[%s] Queue service unreachable", order_id)


def start_grpc():
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10)
    )

    orchestrator_grpc.add_CheckoutResultServiceServicer_to_server(
        CheckoutResultService(),
        server,
    )

    server.add_insecure_port('[::]:50050')
    server.start()

    logging.info("Server started. Listening on port 50050")

    server.wait_for_termination()


if __name__ == '__main__':
    grpc_thread = threading.Thread(
        target=start_grpc,
        daemon=True,
    )

    grpc_thread.start()

    app.run(host='0.0.0.0', threaded=True)