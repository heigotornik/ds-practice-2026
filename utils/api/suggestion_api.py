
import logging
import sys
import os

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
suggestion_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestion'))
sys.path.insert(0, suggestion_grpc_path)
import suggestion_pb2 as suggestion
import suggestion_pb2_grpc as suggestion_grpc

import grpc

logger = logging.getLogger(__name__)

def init_suggestion_data(id, order):
    with grpc.insecure_channel('suggestions:50053') as channel:
        logger.info(f"Initializing suggestion for transaction {id}")
        # Create a stub object.
        stub = suggestion_grpc.SuggestionServiceStub(channel)
        # Call the service through the stub object.
        response = stub.InitOrder(
                suggestion.InitOrderRequest(
                    id=id,
                    order=map_transaction_to_proto(order)
                ))
    return response.ok

def update_vector_clock(id, vc):
    with grpc.insecure_channel('suggestions:50053') as channel:
        logger.info(f"Initializing sending vector clock for order {id} to suggestions")
        # Create a stub object.
        stub = suggestion_grpc.SuggestionServiceStub(channel)
        # Call the service through the stub object.
        response = stub.UpdateStatus(
                suggestion.StatusUpdateRequest(
                    id=id,
                    TransactionServiceA = vc[0],
                    TransactionServiceB = vc[1],
                    FraudDetection = vc[2],
                    Suggestions = vc[3],
                ))
    return response.ok

def map_transaction_to_proto(transaction: dict):
    return suggestion.OrderData(
        user=suggestion.User(
            name=transaction.get("user", {}).get("name", ""),
            contact=transaction.get("user", {}).get("contact", "")
        ),

        creditCard=suggestion.CreditCard(
            number=transaction.get("creditCard", {}).get("number", ""),
            expirationDate=transaction.get("creditCard", {}).get("expirationDate", ""),
            cvv=transaction.get("creditCard", {}).get("cvv", "")
        ),

        userComment=transaction.get("userComment", ""),

        items=[
            suggestion.Item(
                name=item.get("name", ""),
                quantity=item.get("quantity", 0)
            )
            for item in transaction.get("items", [])
        ],

        billingAddress=suggestion.Address(
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
