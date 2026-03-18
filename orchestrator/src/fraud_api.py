import logging
import sys
import os

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

import grpc

logger = logging.getLogger(__name__)

def init_fraud_detection_data(id, order):
    with grpc.insecure_channel('fraud_detection:50051') as channel:
        logger.info(f"Initializing fraud detection for transaction {id}")
        # Create a stub object.
        stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)
        # Call the service through the stub object.
        response = stub.InitOrder(
                fraud_detection.InitOrderRequest(
                    id=id,
                    order=map_transaction_to_proto(order)

                ))
    return response.ok

def check_fraud(order_id):
    # Establish a connection with the fraud-detection gRPC service.
    with grpc.insecure_channel('fraud_detection:50051') as channel:
        logger.debug("Checking fraud for order id %s", order_id)
        # Create a stub object.
        stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)
        # Call the service through the stub object.
        response = stub.DetectFraud(fraud_detection.FraudRequest(id=order_id))
    return response.is_fraud, response.message

def map_transaction_to_proto(transaction: dict):
    return fraud_detection.OrderData(
        user=fraud_detection.User(
            name=transaction.get("user", {}).get("name", ""),
            contact=transaction.get("user", {}).get("contact", "")
        ),

        creditCard=fraud_detection.CreditCard(
            number=transaction.get("creditCard", {}).get("number", ""),
            expirationDate=transaction.get("creditCard", {}).get("expirationDate", ""),
            cvv=transaction.get("creditCard", {}).get("cvv", "")
        ),

        userComment=transaction.get("userComment", ""),

        items=[
            fraud_detection.Item(
                name=item.get("name", ""),
                quantity=item.get("quantity", 0)
            )
            for item in transaction.get("items", [])
        ],

        billingAddress=fraud_detection.Address(
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
