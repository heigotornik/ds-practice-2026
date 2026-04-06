import logging
import sys
import os

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc


import grpc

logger = logging.getLogger(__name__)


def init_verification_data(id, order):
    with grpc.insecure_channel('transaction_verification:50052') as channel:
        logger.info(f"Initializing verification for transaction {id}")
        # Create a stub object.
        stub = transaction_verification_grpc.VerificationServiceStub(channel)
        # Call the service through the stub object.
        response = stub.InitOrder(
                transaction_verification.InitOrderRequest(
                    id=id,
                    order=map_transaction_to_proto(order)

                ))
    return response.ok
    

def map_transaction_to_proto(transaction: dict):
    return transaction_verification.OrderData(
        user=transaction_verification.User(
            name=transaction.get("user", {}).get("name", ""),
            contact=transaction.get("user", {}).get("contact", "")
        ),

        creditCard=transaction_verification.CreditCard(
            number=transaction.get("creditCard", {}).get("number", ""),
            expirationDate=transaction.get("creditCard", {}).get("expirationDate", ""),
            cvv=transaction.get("creditCard", {}).get("cvv", "")
        ),

        userComment=transaction.get("userComment", ""),

        items=[
            transaction_verification.Item(
                name=item.get("name", ""),
                quantity=item.get("quantity", 0)
            )
            for item in transaction.get("items", [])
        ],

        billingAddress=transaction_verification.Address(
            street=transaction.get("billingAddress", {}).get("street", ""),
            city=transaction.get("billingAddress", {}).get("city", ""),
            state=transaction.get("billingAddress", {}).get("state", ""),
            zip=transaction.get("billingAddress", {}).get("zip", ""),
            country=transaction.get("billingAddress", {}).get("country", "")
        ),

        shippingMethod=transaction.get("shippingMethod", ""),
        giftWrapping=transaction.get("giftWrapping", False),
        termsAccepted=transaction.get("termsAccepted", False),
    )
