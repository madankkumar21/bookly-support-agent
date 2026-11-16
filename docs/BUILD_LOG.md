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

## Intent router (2026-10-29, after the review)

The review asked how intent detection works today and at about fifty intents, and how one message with several requests is routed. The answer is now built and measured, off by default: [docs/ROUTER.md](ROUTER.md). The submitted version is tagged `submitted-2026-10-22`.

| Decision | Alternative considered | Why this one |
|---|---|---|
| A Haiku 5.5 call labels each message from a fixed list, through structured output | Embeddings, or a trained classifier | Fastest to stand up and measure. At high volume a trained classifier is cheaper; the labelled set and the eval carry over unchanged |
| The router narrows procedures, never tools | Load only each intent's tools | Changing the tool list breaks the cached prefix, and adds no safety, because the gate already refuses any refund without a confirmed quote. It would also dead-end a misroute, since the procedures call each other's tools. An independent review of the plan caught this before any code |
| A procedure goes into that turn's system message, once, the first time it is needed | Rebuild the system prompt per intent | The system prompt and tools stay byte-identical, so caching and the append-only history hold |
| Anything uncertain loads every procedure: low confidence, an error, an empty answer, a refusal | Trust the label | Uncertain answers widen what loads, so only a confident wrong label can narrow the prompt wrongly. The eval measures that case: none in 159 |
| Code adds what the session already shows: an issued quote loads returns, a verified order loads order status | Trust the router every turn | A misread "yes" can never unload the procedure for a refund in progress |
| A card button skips the router | Classify every turn | The money turn gets no extra latency, and the "[Customer pressed Confirm…]" text has nothing to classify |
| The expected result was written and committed before the first run | Write the targets after seeing the numbers | A target set after the run proves nothing |

| What broke | How it was found | Fix |
|---|---|---|
| My first write-up of the router eval said "11 inexact runs across six items"; the raw runs said 10 across four, and the vague openers had order status added, not returns | Recounting from `runs.jsonl` before committing | Corrected in ROUTER.md; every number there is now read from the run's files |
| "Needed procedure loaded 180 of 180" counted 21 out-of-scope classifications that needed no procedure, so could not miss one | Independent review of the branch | Coverage now counts only the 159 that needed one; the saved runs were re-graded with `--rescore`, no new API calls. Tests for the eval's scoring added (`tests/test_router_eval.py`) |
| "The router can never make the agent worse" was too strong: a confident wrong label narrows the prompt | Independent review | Reworded in `router.py` and here; ROUTER.md names the confident wrong label as the remaining risk |
| The router-off test compared `build_system_prompt()` with itself, so it could not fail | Independent review | It now checks the three procedures in file order, one request per turn, a plain-text facts message and no route row |
| The live two-request check in the web UI was not saved anywhere | Independent review | Re-run from the CLI and saved as `evals/results/2026-10-29-router-haiku/live_multi_request.txt` |


## Jev and the cross-session store (2026-11-13, learning build)

Built after the submission, on the branch `jev-memory`. Not part of the submission. Full write-up: [JEV.md](JEV.md). Run-by-run record: [JEV_LAB_LOG.md](JEV_LAB_LOG.md).

**Decisions I made**
- The question: what does a decision model add to an agent that follows up on a conversation from weeks ago?
- The scope: the router on Jev, recommendations from past orders, and a follow-up on an old case. I left the deal-alert idea out.
- Live Jev calls on fictional data only, with a hard $2 limit.

**Decisions the AI made, which I reviewed in the plan**
- Jev judges language and code decides, with one truth table per decision in `bookly/judgments.py`. Jev stays out of the refund gate, confirmation, eligibility, amounts and dates.
- Memory stores genre keys from a fixed list, never the customer's words, so a planted "I am a VIP" note has nowhere to land.
- Code opens every follow-up, works out its dates and creates the escalation ticket. The conversational model only relays.

**What the independent design review found before any code**
| Finding | Fix |
|---|---|
| With a shared ledger, quote ids repeat across conversations (`Q-1001-1` in each), so a second, legitimate return would be read as already done | One quote counter for the whole store |
| The gate looked a quote up in the ledger before it checked that the conversation issued it. With a shared ledger, a guessed quote id would return another customer's RMA and label | The gate now checks the conversation's own quotes first |
| The gate's check and the ledger write were two steps, so two conversations could both pass | A lock and a per-book recheck inside `record_return` |
| A new file in `procedures/` would change the prompt with the flags off | The new procedure text lives in `prompts/` and loads only with the store on |

**What the tests caught during the build**
| Finding | Fix |
|---|---|
| A second hand-off for the same lost package opened a second follow-up | One follow-up per package; after it escalates, a person owns the case |
| With the flags off, the web page still showed the store's buttons: a `display: flex` rule overrode the `hidden` attribute | A rule that keeps hidden panels hidden; checked in the browser |

**First live run (2026-11-13), reported as it came.** Router on Jev: needed procedure loaded 156 of 159, 91 ms against Haiku's 1,076 ms. Judgments: 94% outcome accuracy, 0 wrong-direction outcomes. Journeys: 6 of 7 pass all three runs, 0 wrong refunds in 39 conversations. The one failed run found a gap in the recommendation tool (no book description to answer from), not a wrong judgment. Jev cost $0.02 in total.

**Second run, after three fixes I asked for (2026-11-13).** Picks carry the catalog description; each genre term gets its own question; the policy intent is two questions. Each wording change was checked on new items it was not written for (12 router items, 4 genre items): all correct. Router 159 of 159. Judgments 97%, 0 wrong direction. Journeys again 6 of 7: the failed run was a simulated customer asking the agent to place an order, which my check did not allow for. I left the check as it was and reported the miss.

**Flags off, nothing changes.** The system prompt and the tool list hash the same on `main` and on this branch (prompt `79d6b291aa511b15`, 7,039 characters; tools `546dd11dc66c5fcd`, 6 tools). The 125 tests from `main` pass unchanged, beside 90 new ones. A test now pins both hashes.

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
