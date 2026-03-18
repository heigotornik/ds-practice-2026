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

from fraud_api import check_fraud, init_fraud_detection_data
from exceptions import FraudulentCheckout, InvalidCheckout
from verification_api import  init_verification_data, verify
from suggestion_api import suggest
from concurrent.futures import ThreadPoolExecutor
# Create a simple Flask app.

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

    verify_future = EXECUTOR.submit(verify, order_id)


    fraud_future = EXECUTOR.submit(check_fraud, order_id)
    suggest_future = EXECUTOR.submit(suggest)

    is_valid, msg = verify_future.result()
    is_fraudulent, _ = fraud_future.result()
    suggestions = suggest_future.result()


    if not is_valid:
        app.logger.error("Checkout validation error: %s", msg)
        raise InvalidCheckout(message=msg)

    if is_fraudulent:
        app.logger.error("Fraudulent checkout detected: %s", msg)
        raise FraudulentCheckout(message="Fraudulent checkout detected")
    
    
    order_status_response = {
        'orderId': '12345',
        'status': 'Order Approved',
        'suggestedBooks': [
            {'bookId': suggestions[0].bookId, 'title': suggestions[0].title, 'author': suggestions[0].author},
        ]
    }

    return order_status_response


if __name__ == '__main__':
    # Run the app in debug mode to enable hot reloading.
    # This is useful for development.
    # The default port is 5000.
    app.run(host='0.0.0.0')
