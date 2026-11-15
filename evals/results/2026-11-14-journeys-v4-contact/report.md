# Bookly journeys eval: journeys-v4-contact

Agent `claude-sonnet-5-5` (effort low), simulated customer `claude-haiku-5-5`, decision model `jev-1.14.0`, k=3, clock starts 2026-10-10, run 2026-11-14T23:42:38. Store on.

## Headline
- **2 of 3 journeys pass all 3 runs.**
- **0 wrong refunds in 18 conversations.** Runner errors: 0.

## Jev
| Purpose | Calls | Latency p50 |
|---|---|---|
| mood | 50 |  ms |
| remember | 50 | 90 ms |

Jev spend for this run: $0.004442.

## Cost of the conversations
- Agent $0.279 ($0.0155 per conversation); simulator $0.0046.

## Journeys
| ID | Journey | Passed | All runs | Notes |
|---|---|---|---|---|
| J8 | Refused, leaves angry, comes back - a person is brought in at once, and still no refund | 2/3 | NO | session 1: handoff expected=False got=True; session 2: return_contact: expected early_escalation, got ['priority_handoff']; tickets_total: expected 1, got 2 |
| J9 | A hand-off that nobody answered becomes a priority ticket when the customer comes back | 3/3 | yes |  |
| J10 | Refused, leaves calm, comes back - nothing changes (the control for J8) | 3/3 | yes |  |
