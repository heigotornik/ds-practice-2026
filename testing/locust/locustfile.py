from locust import HttpUser, task, between


class CheckoutUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def checkout(self):
        payload = {
            "user": {
                "name": "Test User",
                "contact": "test.user@example.com"
            },
            "termsAccepted": True,
            "billingAddress": {
                "street": "Test Street 1",
                "city": "Tallinn",
                "country": "Estonia"
            },
            "creditCard": {
                "number": "4111111111111111",
                "expirationDate": "12/30",
                "cvv": "123"
            },
            "items": [
                {
                    "name": "Clean Code",
                    "quantity": 1
                }
            ]
        }

        with self.client.post(
            "/checkout",
            json=payload,
            timeout=10,
            catch_response=True
        ) as response:
            if response.status_code == 408:
                response.failure("Checkout timed out")
                return

            if response.status_code != 200:
                response.failure(f"Unexpected HTTP status: {response.status_code}")
                return

            try:
                data = response.json()
            except Exception:
                response.failure("Response was not valid JSON")
                return

            status = data.get("status")

            if status != "Order Approved":
                response.failure(f"Checkout was not approved: {data}")
                return

            if not data.get("orderId"):
                response.failure("Approved checkout missing orderId")
                return

            suggested_books = data.get("suggestedBooks")

            if not suggested_books:
                response.failure("Approved checkout missing suggestedBooks")
                return

            first_book = suggested_books[0]

            for field in ["bookId", "title", "author"]:
                if field not in first_book:
                    response.failure(f"Suggested book missing field: {field}")
                    return

            response.success()