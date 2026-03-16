## Events:

(event) a: transaction-verification service verifies if the order items (books) are not an empty list.
(event) b: transaction-verification service verifies if all mandatory user data (name, contact, address…) is filled in.
(event) c: transaction-verification service verifies if the credit card information is in the correct format.
(event) d: fraud-detection service checks the user data for fraud.
(event) e: fraud-detection service checks the credit card data for fraud.
(event) f: suggestions service generates book suggestions.

## Relations

Relation between these events (example partial order):
(a) and (b) can be initiated in parallel (a ‖ b).
(c) can only occur after (a) completes, but it can overlap with (b) if (a) finishes first.
(d) can only occur after (b) completes, but it can overlap with (c) if (b) finishes first.
(e) depends on both (c) and (d) having completed.
(f) depends on (e).

## Case by case analysis of events:

Here is are the possible states of the vector clocks covered for each event.

For each event the required vector clock state is described for which a step/event is run.

### Vector clock and processes

The vector clock: (TV_1, TV_2, F, S)

- TV_1 - Transaction Verification A process. Events: a & c

- TV_2 - Transaction Verification B process. Event: b

- F - Fraud detection. Events: d & e

- S - Suggestion service. Events: f

All processes start their clocks at (0,0,0,0)

### Event (a)

Required clock: 0,0,0,0
Resultant clock: 1,0,0,0

Checks if: (0,0,0,0) < C(event)

Cases:

- **(0,0,0,0) < (0,0,0,0) - initial state**

### Event (c)

Required clock: 1,0,0,0
Resultant clock: 2,0,0,0

Checks if: (1,0,0,0) < C(event)

Cases:

- **(1,0,0,0) < (1,0,0,0) - post event (a)**
- (0,0,0,0) ≮ (1,0,0,0) - initial state

### Event (b)

Required clock: 0,0,0,0
Resultant clock: 0,1,0,0

Checks if: (0,1,0,0) < C(event)

Cases:

- **(0,0,0,0) < (0,1,0,0) - initial state**

### Event (d)

Required clock: 0,2,1,0
Resultant clock: TV_1,TV_2,F+1,S, simple case 0,2,2,0

Checks if: (0,2,1,0) < C(event)
Cases:

- (0,2,1,0) </ (0,0,0,0) - initial state
- (0,2,1,0) </ (3,0,1,0) - only event c finished received
- **(0,2,1,0) < (0,2,1,0) - only event b finished received**
- **(0,2,1,0) < (3,2,2,0) - event b and c finished received**

### Event (e)

Required clock: 3,2,3,0
Resultant clock: TV_1,TV_2,F+1,S, simple case - 3,2,4,0

Checks if: (3,2,3,0) < C(event)
Cases:

- (3,2,3,0) </ (0,0,0,0) - initial state
- (3,2,3,0) </ (3,0,1,0) - only event c finished received
- (3,2,3,0) </ (0,2,1,0) - only event b finished received
- (3,2,3,0) </ (3,2,2,0) - event b and c finished received
- **(3,2,3,0) < (3,2,3,0) - event b and c finished received, d completed**
- (3,2,3,0) </ (0,2,2,0) - event b received & event c finished, event e not received

### Event (f)

Required clock: 3,2,5,1
Resultant clock: 3,2,5,2

Checks if: (3,2,5,1) < C(event)
Cases:

- **(3,2,5,1) < (3,2,5,1) - post event (e) received**
- (3,2,5,1) ≮ (0,0,0,0) - initial state
