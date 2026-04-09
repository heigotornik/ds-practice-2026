# Documentation

## Architecture overview

![Architecture diagram](./images/DS-architecture.svg)

## System overview

Communication between services are performed asynchronously.
The requests to all of the services are sent at the same time, then responses to all are awaited before proceeding with further checks.

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

The fraud detection service is responsible for checking the user
data and credit card information for fraudulent data.

The implementation currently only has simple dummy logic for both subservices.

The fraud detection API currently has the following endpoints:

```proto
service FraudDetectionService{
  rpc UpdateStatus (StatusUpdateRequest) returns (StatusUpdateResponse);
  rpc InitOrder (InitOrderRequest) returns (InitOrderResponse);
}
```

**InitOrder**
This endpoint is used to initialize and cache the order.

**UpdateStatus**
Endpoint for updating the vector clock for a given order.

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
    rpc UpdateStatus (StatusUpdateRequest) returns (StatusUpdateResponse);
    rpc InitOrder (InitOrderRequest) returns (InitOrderResponse);
}

```

**InitOrder**
This endpoint is used to initialize and cache the order.

**UpdateStatus**
Endpoint for updating the vector clock for a given order.

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

**Subservices**

The verification services has two subservices:

- user data verfication
- credit card and books verification

The services have separate vector clocks and event logic.

An overarching worker waits for some condition - either order init or vector clock update to happen - before checking the services, their available events and schedulling them to available threads.

### API

The verification service contains the following API endpoints:

```proto

service VerificationService {
  rpc InitOrder (InitOrderRequest) returns (InitOrderResponse);
}

```

**InitOrder**

This endpoint is used to initialize and cache the order.

```proto
message InitOrderRequest {
  string id = 1;
  OrderData order = 2;
}

message OrderData {
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
message InitOrderResponse {
  bool ok = 1;
}

```

## Order Queue

The Order Queue service maintains a queue of processesed orders.

Orders are added via the orchestrator service after verification, fraud detection and suggestions have been finalized.

Each order is further processed by a queue executor which is the active leader at that specific time.

### API

The Order contains the following API endpoints:

```proto

service OrderQueueService {
    rpc AccessResource(AccessRequest) returns (AccessResponse);
    rpc Enqueue (EnqueueRequest) returns (EnqueueResponse);
    rpc Dequeue (DequeueRequest) returns (DequeueResponse);
}
```

**Enqueue**

The endpoint is used to add an order to the queue. The endpoint call is made by the orchestrator.

```proto
message EnqueueRequest{
  string id = 1;
}

message EnqueueResponse {
  bool ok = 1;
}
```

**Dequeue**

The endpoint is used to dequeue an order from the queue.
This endpoint is used queue exectors. Before the queue executor can call this it endpoint it must request resource access via AccessResource.

```proto
message DequeueRequest{
  string dummy = 1;
}

message DequeueResponse {
  string id = 1;
}
```

**AccessResource**

This endpoint is used to request access to the queue. The request should be made before calling Dequeue.

```proto
message AccessRequest {
  int32 nodeId = 1;
}

message AccessResponse {
  bool ok = 1;
}
```

## Order Executor

The Order Executors process orders by dequeuing an order from the order queue.

A Order Executor can process a order only if it is currently elected as a leader.

### Leader election

The Order Executors perform an election if none of the nodes are elected currently as a leader. The election is done via the Bully Algorithm.

![System diagram](./images/DS-election.svg)

### Mutual exclusion

Mutual exclusion is achieved using the a permission-based, centralized approach.

The leader of the order executors requests access to the Order Queue via AccessResource, before Dequeue.

The order queue itself checks if the resource requester is still using it, if not it forces a release.

### API

The Queue Executor contains the following API endpoints:

```proto

service OrderExecutorService {
  rpc Election(ElectionRequest) returns (ElectionResponse);
  rpc Coordinator(CoordinatorRequest) returns (CoordinatorResponse);
  rpc Heartbeat(HeartbeatRequest) returns (HeartbeatResponse);
  rpc Status(StatusRequest) returns (StatusResponse);
}

```

**Election**

The election call is made by any order executor to other executors. After the call each node starts the election process internally, sending election requests to higher nodes.
If a node either has no-one to send to or receives no responses, it assigns itself as the leader and calls Coordinator on other nodes.

```proto
message ElectionRequest {
  int32 node_id = 1;
}

message ElectionResponse {
  bool ok = 1;
}

```

**Coordinator**

The coordinator call is made by an node that assigns itself as the leader.

```proto
message CoordinatorRequest {
  int32 leader_id = 1;
}

message CoordinatorResponse {
  bool acknowledged = 1;
}

```

**Heartbeat**

This API call is used by executors to check the current leader's status. If a leader should fail, then a failing response from this call will trigger an election.

```proto
message HeartbeatRequest {
  int32 requesting_node = 1;
}

message HeartbeatResponse {
  int32 responding_node = 1;
}
```

**Status**

Status is used by the Order Queue to verify if the Order Executor accessing the resource is still available. If it is either not processing or the node failed the order queue releases the lock.

```proto
message StatusRequest {}

message StatusResponse {
  bool isProcessing = 1;
}
```
