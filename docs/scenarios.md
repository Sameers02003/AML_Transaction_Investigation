# Detection scenarios

## Story: possible layering
A newly onboarded account receives many small transfers from unrelated senders.
The money is quickly split across several beneficiaries and moved onward.
This may have an innocent explanation, so the system creates an alert for human review.
It does not decide that anything illegal happened.

## Rules
**Important:** all numbers below are synthetic demo values chosen for this learning project.
They are NOT regulatory thresholds and must be calibrated and approved before any real use.

| Scenario | Signal | Parameters |
|---|---|---|
| High velocity | Many transfers in a short window | 10 transfers or 500,000 total in 60 minutes |
| Possible structuring | Repeated amounts near a band | 3 transfers between 45,000 and 49,999.99 in 24 hours |
| Rapid in-and-out | Money received then sent out quickly | inflow of at least 50,000, and 80% or more sent out within 60 minutes |
| Fan-in then fan-out | Many senders, then many beneficiaries | 10 or more senders and 4 or more beneficiaries in 60 minutes |
| Profile mismatch | Activity above expected volume | 30-day outgoing above 1.5 times the customer's expected monthly maximum |
| Dormant activation | Quiet account suddenly active | no activity for 90 days, then 3 or more transfers in 24 hours |
| Network cluster | Many-senders-to-many-beneficiaries shape, short cycles nearby, neighbours with open alerts, shared beneficiaries | 24-hour window, 2-hop neighbourhood, institutions excluded, graph score weight 0.15 |
Every rule has automated tests for its boundary, and an ordinary-activity test shows it does not fire on normal behaviour.