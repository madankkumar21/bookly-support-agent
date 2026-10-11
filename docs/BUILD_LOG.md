# Build log

How this was built: the decisions, who made each one, how each was verified, and what broke.
AI coding assistants were used throughout (Claude Code), as the brief expects. This log is the honest split.

## Decisions I made (before any code)

| Decision | Why | Verified by |
|---|---|---|
| Thesis: the model talks, code decides, the customer confirms | In support, a wrong refund costs more than a slow turn | The whole suite; 0 wrong refunds is the guardrail number |
| Two flows deep (returns, order status), policy questions thin | The brief asks for depth; refunds carry every interesting decision | Scope section of the README |
| Eligibility and amounts in a deterministic engine, not the prompt | A pushy customer cannot argue with a function | `tests/test_policy.py`, scenarios R3–R7 |
| Every write needs the customer's own "yes" to a code-rendered card | The model can propose; only the customer releases money | `tests/test_gate.py`, scenarios R8, R9 |
| One policy file feeds both the engine and the quoted text | What the agent says cannot drift from what it does | `tests/test_policy_text.py` (no numbers in text templates), the change test |
| Claude Sonnet 5.5 as the agent, not Opus | Closer to production CX latency and cost; the rules live in code, so the faster model should be enough. Measured, not assumed | Eval report, plus one Opus pass |
| Deterministic eval checks, written before the runs; pass^k with k=5 | One lucky run is not a measurement | `evals/checks.py`, `tests/test_checks.py` |

## Decisions the AI made during the build (and I reviewed)

| Decision | Alternative considered | Why this one |
|---|---|---|
| Hand-written tool loop instead of the SDK tool runner | Tool runner (beta) | The brief asks to orchestrate directly, and the gate and card logic sit between turns |
| A "FACTS SO FAR" mid-conversation `system` message once per customer turn | The `clear_at` beta; text after tool results | GA on Sonnet 5.5, no beta dependency, keeps the history append-only. Trade-off: earlier blocks stay visible, so each block says the latest one wins |
| The confirmation card is rendered by code from the quote, not by the model | Let the model read back the terms | The customer confirms exact code-built terms, and the model cannot paraphrase them wrong |
| `quote_id` is the idempotency key; a new check voids older quotes | A separate model-supplied idempotency key | A model-supplied key can be re-minted on retry; the quote cannot |
| Keyword search over pinned policy passages | Embeddings and a vector store | Nine passages do not need a vector database. Production would retrieve over Bookly's help center |
| Claim check replaces an unbacked "refund issued" reply with a fixed correction | Regenerate the reply once | A second system message cannot follow the first in the same turn, and a code-written correction is deterministic |
| Fixed clock (2026-10-10) and mock data covering every hard case | Live dates | Every run sees the same order ages, so evals are reproducible |
| A scripted fake model for offline tests of the loop, the UI and the API | Only live tests | 78 tests run in about 2 seconds with no API key |

## What broke, and the fix

| What broke | How it was found | Fix |
|---|---|---|
| The planned claim-check regeneration would need two system messages in a row, which the API rejects | Reading the API's placement rules before writing the loop | Replace the reply with a fixed correction, logged in the trace |
| The password check flagged advice ("never share your password") as asking for one | A unit test on the rubric | Ignore matches with a negation just before them |
| The preview server could not use port 8765 (another local process) | Starting the UI preview | Moved the dev-only UI preview to another port |

_Live-run findings are added below after the first eval runs._
