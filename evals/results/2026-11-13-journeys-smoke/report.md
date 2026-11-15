# Bookly journeys eval: journeys-smoke

Agent `claude-sonnet-5-5` (effort low), simulated customer `claude-haiku-5-5`, decision model `jev-1.14.0`, k=1, clock starts 2026-10-10, run 2026-11-13T11:32:36. Store on.

## Headline
- **1 of 1 journeys pass all 1 runs.**
- **0 wrong refunds in 2 conversations.** Runner errors: 0.

## Jev
| Purpose | Calls | Latency p50 |
|---|---|---|
| follow_up | 1 | 112 ms |
| remember | 5 | 132 ms |

Jev spend for this run: $0.000375.

## Cost of the conversations
- Agent $0.0357 ($0.0178 per conversation); simulator $0.0004.

## Journeys
| ID | Journey | Passed | All runs | Notes |
|---|---|---|---|---|
| J6 | Follow-up on a refund, and the customer says it arrived | 1/1 | yes |  |
