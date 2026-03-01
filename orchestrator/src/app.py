import sys
import os

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.

# Import Flask.
# Flask is a web framework for Python.
# It allows you to build a web application quickly.
# For more information, see https://flask.palletsprojects.com/en/latest/
from flask import Flask, request, jsonify
from flask_cors import CORS
import json

from fraud_api import check_fraud
from exceptions import FraudulentCheckout, InvalidCheckout
from verification_api import verify

# Create a simple Flask app.
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
    print("Request Data:", request_data)


    is_valid, msg = verify(request_data)

    if not is_valid:
        raise InvalidCheckout(message=msg)

    is_fraudulent = check_fraud(card_number=request_data.get("creditCard").get("number"), order_amount=len(request_data.get("items")))


    if is_fraudulent:
        raise FraudulentCheckout(message="Fraudulent checkout detected")
    
    order_status_response = {
        'orderId': '12345',
        'status': 'Order Approved',
        'suggestedBooks': [
            {'bookId': '123', 'title': 'The Best Book', 'author': 'Author 1'},
            {'bookId': '456', 'title': 'The Second Best Book', 'author': 'Author 2'}
        ]
    }

    return order_status_response


if __name__ == '__main__':
    # Run the app in debug mode to enable hot reloading.
    # This is useful for development.
    # The default port is 5000.
    app.run(host='0.0.0.0')
