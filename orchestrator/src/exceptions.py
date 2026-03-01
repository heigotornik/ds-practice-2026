

class InvalidCheckout(Exception):
    status_code = 400

    def __init__(self, message):
        super().__init__()
        self.message = message
        self.code = "INVALID_CHECKOUT"

    def to_dict(self):
        rv = dict()
        rv['message'] = self.message
        rv["code"] = self.code
        return {"error": rv}
    

class FraudulentCheckout(Exception):
    status_code = 400

    def __init__(self, message):
        super().__init__()
        self.message = message
        self.code = "FRAUD_CHECKOUT"

    def to_dict(self):
        rv = dict()
        rv['message'] = self.message
        rv["code"] = self.code
        return {"error": rv}