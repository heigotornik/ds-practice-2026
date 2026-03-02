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

from fraud_api import check_fraud
from exceptions import FraudulentCheckout, InvalidCheckout
from verification_api import verify
from suggestion_api import suggest

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


app = Flask(__name__)
# Enable CORS for the app.
CORS(app, resources={r'/*': {'origins': '*'}})


@app.errorhandler(InvalidCheckout)
def invalid_api_usage(e):
    return jsonify(e.to_dict()), e.status_code

@app.errorhandler(FraudulentCheckout)
def invalid_api_usage(e):
    return jsonify(e.to_dict()), e.status_code


# Define a GET endpoint.
@app.route('/', methods=['GET'])
def index():
    """
    Responds with boolean describing fraud or not when a GET request is made to '/' endpoint.
    """
    # Test the fraud-detection gRPC service.
    response = check_fraud()
    # Return the response.
    return str(response)

@app.route('/checkout', methods=['POST'])
def checkout():
    """
    Responds with a JSON object containing the order ID, status, and suggested books.
    """
    # Get request object data to json
    request_data = json.loads(request.data)
    # Print request object data
    app.logger.info("Received checkout: %s", request.data)

    app.logger.debug("Validating checkout")
    is_valid, msg = verify(request_data)

    if not is_valid:
        app.logger.error("Checkout validation error: %s", msg)
        raise InvalidCheckout(message=msg)

    app.logger.debug("Checking fraud")
    is_fraudulent = check_fraud(card_number=request_data.get("creditCard").get("number"), order_amount=len(request_data.get("items")))

    if is_fraudulent:
        app.logger.error("Fraudulent checkout detected: %s", msg)
        raise FraudulentCheckout(message="Fraudulent checkout detected")
    
    suggestions = suggest()
    
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
