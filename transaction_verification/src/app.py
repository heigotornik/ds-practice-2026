import re
import sys
import os

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

import grpc
from concurrent import futures

# Create a class to define the server functions, derived from
# transaction_verification.TransactionVerificationServiceServicer
class VerificationService(transaction_verification_grpc.TransactionVerificationServiceServicer):

    def Verify(self, request, context):
        # These checks were added using ChatGPT 5.2
        # with promt "Add basic validation using the .proto file specified"
        # and adding the .proto file
        # The checks include:
        # - User verification: checks if the user name and contact information are provided.
        # - Terms verification: checks if the terms and conditions are accepted.
        # - Items verification: checks if at least one item is included and if each item has a valid name and quantity.
        # - Credit card verification: checks if the credit card number is in a valid format

        # ---- User verification ----
        if not request.user.name.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="User name is required"
            )

        if not request.user.contact.strip():
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="User contact is required"
            )

        # ---- Terms verification ----
        if not request.termsAndConditionsAccepted:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="Terms and conditions must be accepted"
            )

        # ---- Items verification ----
        if len(request.items) == 0:
            return transaction_verification.VerifyResponse(
                isValid=False,
                message="At least one item must be included"
            )

        for item in request.items:
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

        # ---- Credit card verification ----
        cc = request.creditCard
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

        # ---- Billing address verification ----
        addr = request.billingAddress
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
        return transaction_verification.VerifyResponse(
            isValid=True,
            message="Checkout request verified successfully"
        )

def serve():
    # Create a gRPC server
    server = grpc.server(futures.ThreadPoolExecutor())
    # Add VerificationService
    transaction_verification_grpc.add_VerificationServiceServicer_to_server(VerificationService(), server)
    # Listen on port 50051
    port = "50051"
    server.add_insecure_port("[::]:" + port)
    # Start the server
    server.start()
    print("Server started. Listening on port 50051.")
    # Keep thread alive
    server.wait_for_termination()

if __name__ == '__main__':
    serve()