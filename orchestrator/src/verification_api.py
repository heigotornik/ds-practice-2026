import sys
import os

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc


import grpc

def verify(transaction):
    # Establish a connection with the transaction-verification gRPC service.
    with grpc.insecure_channel('transaction_verification:50052') as channel:
        # Create a stub object.
        stub = transaction_verification_grpc.VerificationServiceStub(channel)
        # Call the service through the stub object.
        response = stub.Verify(map_transaction_to_proto(transaction))
    return response.isValid, response.message


def map_transaction_to_proto(transaction: dict):
    return transaction_verification.Transaction(
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

        discountCode=transaction.get("discountCode", ""),
        shippingMethod=transaction.get("shippingMethod", ""),
        giftMessage=transaction.get("giftMessage", ""),

        billingAddress=transaction_verification.Address(
            street=transaction.get("billingAddress", {}).get("street", ""),
            city=transaction.get("billingAddress", {}).get("city", ""),
            state=transaction.get("billingAddress", {}).get("state", ""),
            zip=transaction.get("billingAddress", {}).get("zip", ""),
            country=transaction.get("billingAddress", {}).get("country", "")
        ),

        giftWrapping=transaction.get("giftWrapping", False),
        termsAndConditionsAccepted=transaction.get("termsAndConditionsAccepted", False),

        notificationPreferences=transaction.get("notificationPreferences", []),

        device=transaction_verification.Device(
            type=transaction.get("device", {}).get("type", ""),
            model=transaction.get("device", {}).get("model", ""),
            os=transaction.get("device", {}).get("os", "")
        ),

        browser=transaction_verification.Browser(
            name=transaction.get("browser", {}).get("name", ""),
            version=transaction.get("browser", {}).get("version", "")
        ),

        appVersion=transaction.get("appVersion", ""),
        screenResolution=transaction.get("screenResolution", ""),
        referrer=transaction.get("referrer", ""),
        deviceLanguage=transaction.get("deviceLanguage", "")
    )