import re
import sys
import os
import sys
from logging.config import dictConfig
import logging

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
from interceptors import LoggingInterceptor
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

import grpc
from concurrent import futures



dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        }
    },
    'handlers': {
        'grpc': {
            'class': 'logging.StreamHandler',
            'stream': sys.stderr,   # Equivalent to Flask wsgi_errors_stream
            'formatter': 'default',
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['grpc']
    }
})

logger = logging.getLogger(__name__)


# Create a class to define the server functions, derived from
# transaction_verification.VerificationServiceServicer
class VerificationService(transaction_verification_grpc.VerificationServiceServicer):

    def __init__(self):
        self.orders = {} 

    def InitOrder(self, request, context):
        logger.info(f"Received InitOrder request for transaction {request.id}")
        self.orders[request.id] = request.order
        return transaction_verification.InitOrderResponse(ok=True)

    def Verify(self, request, context):
        # These checks were added using ChatGPT 5.2
        # with promt "Add basic validation using the .proto file specified"
        # and adding the .proto file
        # The checks include:
        # - User verification: checks if the user name and contact information are provided.
        # - Terms verification: checks if the terms and conditions are accepted.
        # - Items verification: checks if at least one item is included and if each item has a valid name and quantity.
        # - Credit card verification: checks if the credit card number is in a valid format

        # logging added manually
        logger.debug("Received request %s", request)

        if request.id not in self.orders:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Order ID not found. Please initialize the order first."
            )
        
        order = self.orders[request.id]
        logger.debug("Order data for transaction %s exists", request.id)

        # ---- User verification ----
        logger.debug("Running user verification")
        if not order.user.name.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="User name is required"
            )

        if not order.user.contact.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="User contact is required"
            )

        logger.debug("Running terms verification")
        # ---- Terms verification ----
        if not order.termsAccepted:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Terms and conditions must be accepted"
            )

        logger.debug("Running items verification")
        # ---- Items verification ----
        if len(order.items) == 0:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="At least one item must be included"
            )

        for item in order.items:
            if not item.name.strip():
                return transaction_verification.VerifyResponse(
                    isValid=False,
                    message="Each item must have a name"
                )

            if item.quantity <= 0:
                return transaction_verification.VerifyResponse(
                    isValid=False,
                    message=f"Invalid quantity for item '{item.name}'"
                )

        logger.debug("Running credit card verification")
        # ---- Credit card verification ----
        cc = order.creditCard
        cc_number = re.sub(r"[\s-]", "", cc.number)

        if not cc_number.isdigit() or len(cc_number) < 13 or len(cc_number) > 19:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Credit card number format is invalid"
            )

        if not re.match(r"^(0[1-9]|1[0-2])\/\d{2}$", cc.expirationDate):
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Expiration date must be in MM/YY format"
            )

        if not cc.cvv.isdigit() or len(cc.cvv) not in (3, 4):
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="CVV must be 3 or 4 digits"
            )

        logger.debug("Running billing address verification")
        # ---- Billing address verification ----
        addr = order.billingAddress
        if not addr.street.strip() or not addr.city.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Billing address street and city are required"
            )

        if not addr.country.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Billing address country is required"
            )

        # ---- Success ----
        logger.info("All verification checks successful for order ID %s", request.id)
        return transaction_verification.VerifyResponse(
            isValid=True,
            message="Checkout request verified successfully"
        )

def serve():
    # Create a gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(),
                         interceptors=[LoggingInterceptor()])
    # Add VerificationService
    transaction_verification_grpc.add_VerificationServiceServicer_to_server(VerificationService(), server)
    # Listen on port 50052
    port = "50052"
    server.add_insecure_port("[::]:" + port)
    # Start the server
    server.start()
    logger.info("Server started. Listening on port 50052.")
    # Keep thread alive
    server.wait_for_termination()

if __name__ == '__main__':
    serve()