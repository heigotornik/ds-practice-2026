# Documentation

## Architecture overview

![Architecture diagram](./images/DS-architecture.svg)

## System overview

![System diagram](./images/DS-system-diagram.svg)

## Orchestrator Service

## Fraud Detection Service

## Suggestions Service

## Verification Service

### Overview

The verification service is responsible for verifying the checkout request conforms to all relevant business rules.

The verification services covers:

- that required fields are present
- fields are in the correct format

Checks present in the verification service currently include:

- User verification: checks if the user name and contact information are provided.
- Terms verification: checks if the terms and conditions are accepted.
- Items verification: checks if at least one item is included and if each item has a valid name and quantity.
- Credit card verification: checks if the credit card number, CVV and expiration are in a valid format
- Billing address verification: checks if required billing address values are filled

### API

The verification service contains the following API endpoints:

```proto

service VerificationService {
  rpc Verify (Transaction) returns (VerifyResponse);
}

```

**verify**

The request body is equivalent to the checkout object received from the frontend.

The gRPC struct to use is `Transaction`.

```proto
message Transaction {
  User user = 1;
  CreditCard creditCard = 2;
  string userComment = 3;

  repeated Item items = 4;

  Address billingAddress = 5;

  string shippingMethod = 6;
  bool giftWrapping = 7;
  bool termsAccepted = 8;
}

message User {
  string name = 1;
  string contact = 2;
}

message CreditCard {
  string number = 1;
  string expirationDate = 2;
  string cvv = 3;
}

message Item {
  string name = 1;
  int32 quantity = 2;
}

message Address {
  string street = 1;
  string city = 2;
  string state = 3;
  string zip = 4;
  string country = 5;
}
```

The response returned is

```proto
message VerifyResponse {
  bool isValid = 1;
  optional string message = 2;
}
```
