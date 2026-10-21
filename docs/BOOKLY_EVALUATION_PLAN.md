# Bookly evaluation plan: what we would sign before the build

How this prototype becomes a decision Bookly can defend. One page, agreed with Bookly's CX lead and executive sponsor before any build starts.

## Before the build

Build a test set: real Bookly return and order-status tickets, with the correct outcome written beside each one by Bookly's CX lead. Agree the pass criteria below at the same time. The simulated customers in this prototype come from my assumptions; the test set comes from Bookly's customers.

## Exit criteria, signed before the build

| Criterion | Target | How it is measured | What this prototype shows |
|---|---|---|---|
| Resolved correctly on the test set | Set with Bookly from its current numbers | Code compares each conversation's outcome with the outcome the CX lead wrote beside the ticket | 16 of 16 scenarios, each played 5 times by a simulated customer (80 conversations) |
| Wrong refunds | 0 | Every refund the agent made must match the expected list exactly | 0 in 80 conversations |
| Cases that must reach a person | 100% | The handoff to a person, and the ticket it creates, are checked | 21 of 80 ended with a person; every required one did |
| Policy answers match Bookly's written policy | 100% | One policy file feeds both the decision and the text the agent quotes; a test fails if any number is typed into the text by hand | 3 of 3 policy scenarios, 5 of 5 |
| Speed | Slowest 1 in 20 replies under the agreed limit | Measured per reply | Typical reply 4.2 s; slowest 1 in 20 replies 8.7 s |
| Cost per conversation | Under the agreed figure | Claude API cost at list price; hosting not included | About $0.013 |
| **Ownership: Bookly's CX lead changes one policy value and re-runs the test suite, with no engineer** | Under 15 minutes | Timed; the suite reports what changed | One value changed, the change-of-mind return window, from 30 to 14 days. The re-run cost about $1 and reported the two expected refund changes and no other |

## What Bookly's team runs themselves

1. Edit a value in `bookly/data/policy.yaml`. The decision rules and the policy text the agent quotes both read from it.
2. Re-run the test suite, which replays all 80 conversations: `uv run python -m evals.run_evals --k 5` (about $1).
3. Run the code tests: `uv run pytest`.

To try a change without editing the file: `uv run python -m evals.run_evals --k 5 --override returns.print_return_window_days=14`.

## Rollout

Offline on the test set first. Then shadow mode: the agent drafts, a person sends. Then 1%, 5% and 10% of live traffic. Each stage ends with a results review with the executive sponsor: the saving formula with Bookly's own numbers in it, and the wrong-refund rate beside it. After go-live, every refund and every handoff is logged, Bookly's CX lead reviews them weekly, and any policy edit re-runs the test suite before it ships.

## A Bookly-specific risk to plan for

**January gift returns.** The person returning a gift is not the buyer, so gift returns need their own identity step, such as a gift-receipt code.

## Business case

Monthly saving = contacts per month × share that are order status or returns × resolution rate × (Bookly's cost per human contact − $0.013). Measured here: the AI cost per conversation. Bookly supplies its volume, its contact mix and its human cost. The real resolution rate comes from its own test set.
