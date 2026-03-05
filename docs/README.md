# Documentation

## Architecture overview

![Architecture diagram](./images/DS-architecture.svg)

## System overview

Communication between services are performed synchronously.

![System diagram](./images/DS-system-diagram.svg)

## Orchestrator Service

### Overview

The orchestrator service provides REST endpoints for interacting with the book store.
This service is responsible for communicating with the different microservices via gRPC.

### API

The verification service contains the following REST endpoints:

- POST /checkout

**POST /checkout**

The endpoint receives the user checkout request, then:

- sends it to the validation service
- then if valid, to the fraud check service
- the if valid to the suggestion service.

and finally returns the checkout with its status and book suggestions.

## Fraud Detection Service

### Overview

The fraud detection service is responsible for analysing the checkout of the user and checking if the checkout is fraudulent or not.

The current implementation simply checks if the card number contains "1234" repeating 4 times ("1234123412341234") and if it does, it returns that the checkout is fraudulent.

### API

The verification service contains the following API endpoints:

```proto

service FraudDetectionService {
    rpc DetectFraud (FraudRequest) returns (FraudResponse);
}

```

**DetectFraud**

The request body a subset of the checkout object received from the frontend, containing
a list of books that contained in the checkout object. Every entry in this list contains
the book's id, title and author.

```proto
message FraudRequest {
    string card_number = 1;
    float order_amount = 2;
}

message FraudResponse {
    bool is_fraud = 1;
}
```

## Suggestions Service

### Overview

The suggestion service is responsible for suggesting books to the user based on their
previous purchases.

The current implementation simply reads in the list of books in an order and returns
a single test book.

### API

The verification service contains the following API endpoints:

```proto

service SuggestionService {
    rpc SuggestBooks (BookList) returns (BookList);
}

```

**suggest**

The request body a subset of the checkout object received from the frontend, containing
a list of books that contained in the checkout object. Every entry in this list contains
the book's id, title and author.

```proto
message BookList {
    repeated Book books = 1;
}
message Book{
    int32 bookId = 1;
    string title = 2;
    string author = 3;
}
```

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
