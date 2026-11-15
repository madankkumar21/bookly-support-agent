# Bookly journeys eval: journeys-v3-j1

Agent `claude-sonnet-5-5` (effort low), simulated customer `claude-haiku-5-5`, decision model `jev-1.14.0`, k=3, clock starts 2026-10-10, run 2026-11-13T17:58:56. Store on.

## Headline
- **1 of 1 journeys pass all 3 runs.**
- **0 wrong refunds in 6 conversations.** Runner errors: 0.

## Jev
| Purpose | Calls | Latency p50 |
|---|---|---|
| recommend | 3 | 112 ms |
| remember | 18 | 112 ms |

Jev spend for this run: $0.001944.

## Cost of the conversations
- Agent $0.1389 ($0.0231 per conversation); simulator $0.0018.

## Journeys
| ID | Journey | Passed | All runs | Notes |
|---|---|---|---|---|
| J1 | Recommend from history, in a later conversation | 3/3 | yes |  |
