# Build log

How this was built: the decisions, who made each one, how each was verified, and what broke.
AI coding assistants were used throughout (Claude Code), as the brief expects. This log is the honest split.

## Decisions I own (made before any code)

Several were sharpened by independent reviews of my plan before I built anything: the thesis wording, `quote_id` as the idempotency key, the whole-message allowlist, and reading back the reason before the customer confirms. I accepted those changes, and I can defend each one.

| Decision | Why | Verified by |
|---|---|---|
| Thesis: the model talks, code decides, the customer confirms | In support, a wrong refund costs more than a slow turn | The whole suite; 0 wrong refunds is the guardrail number |
| Two flows deep (returns, order status), policy questions thin | The brief asks for depth; refunds carry every interesting decision | Scope section of the README |
| Eligibility and amounts in a deterministic engine, not the prompt | A pushy customer cannot argue with a function | `tests/test_policy.py`, scenarios R3–R7 |
| Every write needs the customer's own "yes" to a code-rendered card | The model can propose; only the customer releases money | `tests/test_gate.py`, scenarios R8, R9 |
| One policy file feeds both the engine and the quoted text | What the agent says cannot drift from what it does | `tests/test_policy_text.py` (no numbers in text templates), the change test |
| Claude Sonnet 5.5 as the agent, not Opus | Closer to production CX latency and cost; the rules live in code, so the faster model should be enough. Measured, not assumed | Eval report, plus a k=5 Opus run at equal effort |
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
| A scripted fake model for offline tests of the loop, the UI and the API | Only live tests | The whole suite runs in about 2 seconds with no API key |

## What broke, and the fix

| What broke | How it was found | Fix |
|---|---|---|
| The planned claim-check regeneration would need two system messages in a row, which the API rejects | Reading the API's placement rules before writing the loop | Replace the reply with a fixed correction, logged in the trace |
| The password check flagged advice ("never share your password") as asking for one | A unit test on the rubric | Ignore matches with a negation just before them |
| The preview server could not use port 8765 (another local process) | Starting the UI preview | Moved the dev-only UI preview to another port |

## What the live runs found (2026-10-13)

| What broke | How it was found | Owning layer | Fix |
|---|---|---|---|
| "Do you ship to Canada?" retrieved shipping times and costs, not the regions passage. The agent correctly said it did not know | Demo 3, the first live run | Retrieval | Light stemming, and keywords that few passages share count for more. A regression test covers nine phrasings |
| The simulated customer in P1 went off-script (asked about Canada shipping cost), then asked for a person. The agent's handoff was correct | Smoke run, 15 of 16 | The scenario | Persona limited to its two questions. The check was not loosened |
| The claim check replaced a correct "No return or refund was created" after a cancellation: a false block by my own guardrail | k=5 run, R8 failed 1 of 5 | The guardrail | Negation cancels a claim, judged per clause. The exact sentences are now tests. It then fired in 0 of 80 conversations |
| API key not scoped to a workspace (400) | The first live call | Setup | `make_client()` sends `anthropic-workspace-id` when `ANTHROPIC_WORKSPACE_ID` is set; a workspace key was used instead |
| API credit ran out mid-way through the first change-test run; 45 runs errored and an unaffected scenario looked like it moved | The run's output | The runner | The runner stops at the first credit error and flags the run as incomplete. That output was set aside, not reported |
| The R3 check had "30" hard-coded, so it failed under the 14-day change test even though the agent correctly said "14 days" | Change test | The test | Text checks now read `{policy.key}` values from the active policy, the same rule the agent follows |
| Two rubric false positives: "send you a link to reset your password" counted as asking for a password, and a first name taken from the customer's own email counted as a leak | Opus comparison run | The rubric | Exact-sentence tests; every saved run re-graded with `evals/rescore.py` at no API cost. The Sonnet verdicts were unchanged |

Results after the fixes:
- **Sonnet 5.5:** 16 of 16 scenarios pass^5, 0 wrong refunds in 80 conversations, $0.013 per conversation.
- **Change test (14-day window):** R10 and R8 changed outcome, both as predicted; no other outcome changed; 16 of 16 passed.
- **Opus 5.5 at equal effort:** 15 of 16, with one real error (a handoff the customer declined, with a "placeholder" summary), at $0.025 per conversation.

Lesson: three of the five failures the evals found were in my own checks or scenarios, not in the agent. A rubric needs the same tests as the code it grades.


## What the independent review of the finished build found (2026-10-13)

| Finding | Owning layer | Fix |
|---|---|---|
| The README said only R10 moved in the change test. R8 moved too, exactly as the suite predicted | The write-up | Reworded: two scenarios moved, both ones a 14-day window should move |
| "0 wrong refunds in 80" did not say that in 50 of the 80 the engine made a refund impossible, or that the gate never had to block a write live | The write-up | The README now splits the 80 and says the gate's blocking paths are proven by unit tests |
| "ok", "okay", "sure" and "sounds good" counted as a yes to money. In two R8 runs a typed decline was read as unclear and the card stayed open; under that allowlist, a following "ok" would have released a refund. No run typed one | The gate | Removed from the allowlist, with tests. No reported run used them, so no verdict changes |
| The Confirm button was not bound to its card. A click on an older card would confirm the newest terms | The gate and the UI | Each button sends its card's `quote_id`; a mismatch is "stale_card" and confirms nothing; older cards are disabled. Tests added |
| The eval reports printed an illustrative dollar saving from assumed inputs | The report | Removed. The report shows the formula, the measured AI cost, and what Bookly supplies |

**Which code the reported runs used.** The three reported runs were made before the last two fixes. Those fixes touch only paths the runs did not use: no run typed a weak acknowledgement to confirm, and the evals drive the agent directly, not through the web UI.

**Time and history.** The brief estimates about 4 hours, and this took longer. Commit dates were reset when I changed the commit email to my GitHub noreply address, so git timestamps are not a time log.
