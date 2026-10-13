# If this were a Bookly POV

How I would take this from a prototype to a decision Bookly can defend.

## First, before any build
Build a golden set from Bookly's real return and order-status tickets, and agree the rubric with their CX lead. Synthetic customers test my assumptions, not Bookly's customers.

## Exit criteria, signed before the build
The targets get agreed with Bookly:
- verified resolution at or above the target on the golden set
- 0 wrong refunds at pass^5 on the adversarial set
- every must-escalate case escalates
- every policy claim is grounded in their policy text
- p95 latency under the agreed limit
- their CX lead changes one policy value and re-runs the suite in under 15 minutes, with no engineer

## Rollout
Offline first, then shadow mode, then 1%, 5% and 10% of traffic.

## Bookly-specific risk to plan for
**January gift returns.** The person returning a gift is not the buyer, so gift returns need their own identity step, such as a gift-receipt code.

## Business case: a formula, not a forecast
- **Monthly saving** = Bookly's contacts per month × share that are order status or returns × resolution rate × (Bookly's cost per human contact − AI cost per conversation).
- **Measured in this build:** the AI cost per conversation (about $0.013, estimated at list prices). The resolution rate here is on synthetic scenarios and proves the method, not Bookly's number.
- **Bookly supplies:** its volume, its contact mix and its human cost. The real resolution rate comes from its golden set.
- **Guardrail:** the wrong-refund rate is reported next to any saving.

## Line of sight
- **Now:** returns and order status, the high-volume, money-moving contacts.
- **Next:** exchanges and store-credit offers that keep revenue, proactive delay messages, and voice.
- **Later:** journeys beyond support.
