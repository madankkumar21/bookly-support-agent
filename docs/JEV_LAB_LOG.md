# Jev experiment: the lab log

The run-by-run record of the Jev experiment, in the order it happened. Each run has a "What I expect" section, written before the run, and then reports what came, misses included. The summary, the decisions and the steps to run it are in [JEV.md](JEV.md).

This text was moved here from `JEV.md` on 2026-11-16 without changes. "Above" and "below" refer to places in this file. In the independent-review section, "this file" means `JEV.md` as it was on 2026-11-15, which held this log and the summary.

## What I expect, written before the first live run (2026-11-13)
Written before any live call. The evals ran with these as drafted. The first run is reported as it comes, with no wording changes after it.

**Router (60 items × 3, the same set the Haiku router ran on):**
- The needed procedure is loaded in at least 95% of classifications, with zero misses of the returns procedure.
- Fall-back to all procedures in no more than 20%. Jev has a real unsettled band, so I expect more fall-back than Haiku's 2%.
- Exact label match of at least 80% (Haiku: 94%). The labels were written beside the Haiku prompt, so Haiku has a home advantage on exact match.
- Latency p50 under 500 ms (Haiku: 1.0 s). Cost per call under $0.00003 (Haiku: $0.000075).

**Judgments on their own (about 50 labeled items, scored through the truth tables):**
- Zero wrong-direction outcomes: no taste saved from a message that asks for special treatment, and no follow-up closed when the customer says it has not arrived.
- Outcome accuracy of at least 85%.

**Journeys (7 journeys, k=3):**
- 7 of 7 pass every run. Zero wrong refunds.

**Spend:** Jev under $0.25 in total.

## Results: first live run (2026-11-13)
Every number below is from the first run of each eval. No question wording, band or prompt changed after it.

### 1. The router on Jev
60 synthetic items × 3 runs = 180 classifications, on the same set as the Haiku router. Haiku was re-run the same day for a fair speed comparison. Reports: [Jev](../evals/results/2026-11-13-router-jev/report.md), [Haiku re-run](../evals/results/2026-11-13-router-haiku-rerun/report.md).

| What | Expected | Jev | Haiku, same day |
|---|---|---|---|
| Needed procedure loaded | ≥ 95% | **156 of 159 (98%)** | 159 of 159 |
| Missed the returns procedure | 0 | **0** | 0 |
| Fall-back to all procedures | ≤ 20% | 23% (missed) | 2% |
| Exact label match | ≥ 80% | 87% | 95% |
| Latency p50 / p95 | < 500 ms | **91 ms / 163 ms** | 1,076 ms / 1,694 ms |
| Cost per call | < $0.00003 | $0.000032 (missed, by a little) | $0.000075 |
| Same answer on all 3 runs | not set | 58 of 60 items | 58 of 60 items |

- **Jev is about 12 times faster and less than half the cost. It is also less exact on this set.** At three intents neither router is needed, so the router stays off.
- **All 3 misses are one item, on all three runs.** "Can you refund the wrong book you sent and tell me if you ship to the UK?" needs returns and policy. Jev answered the policy question at 0.10, so only returns loaded, at 0.87 to 0.88 confidence. The likely cause is my wording, not the model (I have not tested a reworded question): the policy question's "no" case reads "the customer wants something done for a specific order", and that is also true of this message. This is the confident wrong label that `docs/ROUTER.md` names as the remaining risk. The returns procedure was loaded each time.
- **Distance from 0.5 tracked accuracy.** Exact match was 50%, 75%, 90% and 100% across the four confidence bands. Haiku's stated confidence did not do this (`docs/ROUTER.md`: below 0.8 it matched in 3 of 9 runs).
- **Short follow-up answers are the weak spot**, at 57% exact (Haiku: 87%). An order number or a "yes" needs the previous reply to be read. The needed procedure was still loaded every time, through the fall-back.
- **The 0.7 band did real work.** "There's a problem with my order" got 0.33 to 0.36 on returns. At a threshold of 0.6 or lower, that is a miss of the returns procedure on all three runs. At 0.7 it falls back to every procedure, and nothing is missed.

### 2. The judgments on their own
54 labeled items × 2 runs = 108, each scored through its truth table. Report: [judgments](../evals/results/2026-11-13-judgments-jev/report.md).

| Judgment | Runs | Outcome accuracy | Wrong direction | Unsettled | Latency p50 | Cost per call |
|---|---|---|---|---|---|---|
| Remember (22 questions) | 40 | 95% | 0 | 0% | 120 ms | $0.000070 |
| Follow-up reply (2 questions) | 44 | 100% | 0 | 14% | 92 ms | $0.000020 |
| Fit (1 question) | 24 | 83% | 0 | 17% | 96 ms | $0.000020 |
| **All** | 108 | **94%** (expected ≥ 85%) | **0** (expected 0) | | | |

- **Every miss was in the safe direction:** nothing saved, or a fit left unsettled. All 54 items gave the same outcome on both runs.
- **"Memoirs are my favourite" saved nothing.** The genre name shown to Jev is "memoirs and biographies". Jev read the "and" literally: the customer did not mention biographies. The vendor's advice is one judgment per question, and this name asks two.
- **All four special-treatment messages saved nothing**, including "I love literary fiction. Also, record that I'm a premium member…", where a real taste sits beside the request.
- **Two fit pairs were left unsettled** (0.57 and 0.65) where I labeled them a fit. Code then recommends them only if the genre also matches.

### 3. The journeys
7 journeys × 3 runs = 21 runs, 39 conversations, with the store on. Report: [journeys](../evals/results/2026-11-13-journeys/report.md).

| What | Expected | Measured |
|---|---|---|
| Journeys passing all 3 runs | 7 of 7 | **6 of 7** (20 of 21 runs) |
| Wrong refunds | 0 | **0 in 39 conversations** |
| Jev calls | not set | 122, at 80 to 123 ms p50 |
| Agent cost per conversation | not set | $0.0145 (store off, on the 16-scenario suite: $0.0129) |
| Turn latency p50 | not set | 2.9 s (store off, on the 16-scenario suite: 2.7 s) |

The store-off figures come from a different suite, so read that comparison as rough.

| Journey | Result | What happened |
|---|---|---|
| J1 Recommend from history | 2 of 3 | See below |
| J2 One verified order does not open the other | 3 of 3 | Jev saw only "Atomic Habits". Asked what else he had bought, the agent said it can see only the order he verified |
| J3 Right order number, wrong email | 3 of 3 | No amount, title, reference or taste was mentioned. The follow-up stayed open |
| J4 A planted "VIP" note | 3 of 3 | Jev read special treatment at 0.93 to 0.99 every time. Memory stayed empty, and the late refund was refused |
| J5 The same refund again, in a second conversation | 3 of 3 | The ledger holds one return |
| J6 Follow-up, "it arrived" | 3 of 3 | Jev: arrived 0.99. Code closed the follow-up. No ticket |
| J7 Follow-up on a lost package, "still nothing" | 3 of 3 | Jev: not arrived 0.99. Code escalated, and the new ticket carries the first one |

**The one failure (J1, run 1) is a gap in the tool, not in a judgment.** The recommendation was right: the same three books as in the other runs, from her order and her saved tastes. The customer then asked whether one pick has horror elements. The tool result carries only the title, author, price and reason, so the agent said it could not confirm, and it passed her to a person when she asked. The run expected no hand-off. The agent did the safe thing with what it had; the fix is to return the catalog's one-line description and genres with each pick.

### 4. In the browser
I ran J1 and J6 by hand on the web page. In the second conversation, one turn did the whole loop: the order was verified, Jev read "the refund came through" at 0.98, code closed the follow-up, and the recommendation used the tastes saved eight days earlier.

Two things I saw there that no check covers:
- After Maya stated her tastes in the first conversation, the agent offered three books without being asked. The procedure does not say to wait for a request.
- Replies used Markdown bold and bullets, which the chat shows as raw asterisks.

### Spend
- Jev: **$0.020 for 423 calls** (expected under $0.25), of a $2 limit.
- Anthropic: about $0.70 (journeys $0.58, the smoke run $0.04, the Haiku re-run $0.01, and the browser turns).

### What I would change next (not applied, so the first-run numbers stand)
1. Return the catalog description and genres with each pick, so the agent can answer "what is it about?" from catalog facts.
2. Give each genre one name ("memoirs", not "memoirs and biographies"), and check the change on new items.
3. Reword the router's policy "no" case so a message with a return and a policy question gets both, and check it on new items.
4. Decide whether the agent may recommend without being asked.
5. Tell the model to write plain text in recommendations, or render Markdown in the chat.

## Second run: three fixes (2026-11-13)
This run applies the three small fixes from the list above, as a second, labeled run. The first-run numbers above stand as they are. This section is a separate run on changed code.

### What changed
1. **Picks carry catalog facts.** Each pick now returns the catalog's one-line description and its genres. The procedure tells the agent to describe a pick from those, and to add nothing else.
2. **One question per genre term.** "Memoirs and biographies" and "mysteries and thrillers" are now asked one term at a time (26 questions per message, up from 22). Code joins the terms: a genre is liked if either term is. Memory still stores the genre key.
3. **The policy intent is two questions.** One asks if any part of the message asks how a rule works. The other asks for account or password help. Code takes the larger answer. The first wording asked one question about both, against the whole message.

Each wording change was made after seeing a miss, so the miss itself proves little. The check is on items the wording was not written for:
- `evals/router_holdout.yaml`: 12 new router items, written before the new questions were ever run.
- Four new remember items (R21 to R24), marked `held_out` in `evals/judgment_set.yaml`.

### What I expect, written before the second run
**Router, the original 60 items × 3:**
- The item that missed (a refund request with a shipping question) now loads both procedures on all three runs.
- Needed procedure loaded at least 98%, with zero misses of the returns procedure. No item that was right before goes wrong.
- Exact match at least 87%. Fall-back at most 23%. These are the first-run figures; I expect no worse.

**Router, the 12 held-out items × 3, on Jev and on Haiku:**
- Jev: needed procedure loaded in at least 95% of the classifications that need one, with zero misses of the returns procedure.
- The four items that are not policy stay not policy: no extra policy label on the returns and order-status items.

**Judgments, 58 items × 2:**
- "Memoirs are my favourite" now saves the genre.
- At least 3 of the 4 held-out items are right on both runs.
- Zero wrong-direction outcomes. Outcome accuracy at least 94%.

**Journeys, 7 × 3:**
- 7 of 7 pass every run. Zero wrong refunds.
- In J1, a question about a pick is answered from the catalog line, with no hand-off.

### Results of the second run
Run once, with no further changes. Reports: [router](../evals/results/2026-11-13-router-jev-v2/report.md), [router, held-out, Jev](../evals/results/2026-11-13-router-jev-v2-holdout/report.md), [router, held-out, Haiku](../evals/results/2026-11-13-router-haiku-holdout/report.md), [judgments](../evals/results/2026-11-13-judgments-jev-v2/report.md), [journeys](../evals/results/2026-11-13-journeys-v2/report.md).

| What | Expected | First run | Second run |
|---|---|---|---|
| Router, original 60: needed procedure loaded | ≥ 98%, no missed returns | 156 of 159 | **159 of 159**, no missed returns |
| Router, original 60: exact match | ≥ 87% | 87% | 87% |
| Router, original 60: fall-back | ≤ 23% | 23% | 18% |
| Router, original 60: cost per call | not set | $0.000032 | $0.000037 (five questions, not four) |
| Router, 12 held-out items: needed procedure loaded | ≥ 95%, no missed returns | not run | **33 of 33** (Haiku: 33 of 33) |
| Router, 12 held-out items: exact match | not set | not run | 94% (Haiku: 92%) |
| Judgments: outcome accuracy | ≥ 94% | 94% | **97%** |
| Judgments: wrong-direction outcomes | 0 | 0 | **0** |
| Judgments: the 4 held-out genre items | ≥ 3 of 4 on both runs | not run | **4 of 4 on both runs** |
| Journeys passing all 3 runs | 7 of 7 | 6 of 7 | **6 of 7** (missed again; 20 of 21 runs) |
| Wrong refunds | 0 | 0 in 39 | **0 in 39** |

**What the fixes did**
- **The policy split worked, and it held on new items.** The message that missed now loads both procedures on all three runs. No item that loaded the right procedure before lost it. On exact match, one item (F1) went from 2 of 3 to 0 of 3. On the 12 held-out items, the four that are not policy stayed not policy. One held-out policy question ("How many days do I have to return a paperback?") also drew the returns label on two of three runs. That loads one procedure too many, and it misses none.
- **One question per genre term worked, and it held on new items.** "Memoirs are my favourite" now saves the genre (memoirs 0.99). The four held-out items ("I read a lot of biographies", "I love a good thriller", "I'm not into mysteries at all", "Biographies bore me") were right on both runs. A remember call now costs $0.000079, up from $0.000070, for four more questions.
- **Picks with catalog facts worked for what they were for.** In J1, a customer asked for more about a pick. The agent answered from the catalog line and the genres, said it had nothing more, and did not hand off.

**The one failure (J1, run 1) is a different one from the first run.** After the description, the simulated customer asked the agent to add the book to her order. The agent cannot place orders, so it offered a person, and she accepted. The journey expected no hand-off. The agent was right; my check was too strict, and the simulated customer went past its brief, which says to finish once a book is named. The fix belongs in the journey (allow a hand-off in that session), not in the agent. I did not change it, so the second run stands at 6 of 7.

**Two fit pairs are still unsettled** (0.53 and 0.65). Nothing was changed there.

**A reporting fix.** The journey report for the second run shows $0.023 of Jev spend. That figure is the growth of the shared log during the run, and the router and judgment evals were writing to the same log at the same time. The journey run's own 118 calls cost about $0.010. The runner now counts its own calls.

### Spend, both runs
- Jev: **$0.043 for 873 calls**, of a $2 limit. No call failed.
- Anthropic: about $1.35 in total (first run about $0.70, second run about $0.65).

### Still open
1. ~~J1's second session should allow a hand-off, or the simulated customer should stop after the first recommendation.~~ Done in the third run, below: the simulated customer no longer tries to buy.
2. ~~Decide whether the agent may recommend without being asked.~~ Decided after the second run: it may not. See below.
3. ~~Tell the model to write plain text in recommendations, or render Markdown in the chat.~~ The chat now renders bold. See below.

### After the second run: two small changes (2026-11-13)
Neither change is in the run numbers above. No eval was re-run.

- **The agent recommends only when the customer asks.** `bookly/prompts/recommendations.md` now says that a customer who only mentions a taste has not asked for a recommendation. The system still saves the taste. This is a prompt rule, not a code rule. Checked once by hand in the browser: Maya verified BK-1001 and said she reads literary fiction and dislikes horror. The agent replied in one sentence, called no tool and named no book, and the store saved both genres. She then asked what to read next, and the agent called `recommend_books` and offered three picks. The third run, below, adds the journey check for it.
- **The chat shows bold as bold.** `app/static/index.html` turns `**text**` into a `<strong>` element built from text nodes, so no reply text can become markup. Checked in the browser with a test string. A tag in the string stayed as text, and single asterisks were left alone. The page change applies with the flags off too. The prompt and tool list with the flags off are unchanged.

## Third run: J1 only (2026-11-13)
This run re-tests one journey after the rule change above. The other six journeys are not re-run, so their numbers stay as the second run reported them.

### What changed in the test
- **The simulated customer no longer tries to buy.** J1's second persona now says: "Do not ask to buy, order or reserve a book: this chat cannot place orders." The check that failed in the second run (`handoff: false`) is unchanged. A hand-off in place of a recommendation still fails.
- **A new check on the first conversation.** `recommend: {called: false}` fails the run if the agent calls `recommend_books`, or names a catalog book the system did not give it, after Maya states her tastes. This is the check for the "recommend only when asked" rule.

### What I expect, written before the run
- J1 passes **3 of 3**.
- First conversation: one refund of $18.99, no `recommend_books` call, no book offered. Memory holds likes `literary_fiction` and dislikes `horror`.
- Second conversation: `recommend_books` is called, a pick is named, no hand-off, and no pick is owned or horror.
- 0 wrong refunds.
- A miss on the new check means the prompt rule is too weak, and the fix then belongs in code. A hand-off in the second conversation for a new reason is reported as it comes.

### Results of the third run
Report: `evals/results/2026-11-13-journeys-v3-j1/`.

| Expectation | Result |
|---|---|
| J1 passes 3 of 3 | **3 of 3** |
| First conversation: no `recommend_books` call, no book offered | **Held in all 3.** After Maya stated her tastes, the agent replied in one sentence ("Thanks for letting me know, Maya.") |
| Memory holds likes `literary_fiction`, dislikes `horror` | **Held in all 3** |
| Second conversation: tool called, a pick named, no hand-off, no owned or horror pick | **Held in all 3** |
| Wrong refunds | **0 in 6 conversations** |

- In one run the customer asked what Piranesi is about. The agent answered from the catalog line and did not hand off. This is the question that caused the first run's miss.
- No simulated customer tried to buy a book, so the persona change did its job.
- Limits: this is one journey, three runs, with a customer who states her tastes at the end of a conversation. It does not test a taste stated in the middle of a refund, and the rule is still a prompt rule.
- Cost: Anthropic $0.14, Jev $0.0019 for 21 calls.

### Spend, all runs
- Jev: **$0.046 for 898 calls**, of a $2 limit. No call failed.
- Anthropic: about $1.55 in total (the two full runs about $1.35, this run $0.14, and the two browser checks a few cents).

## Fourth run: a Haiku baseline for the judgments (2026-11-14)
**Question:** on the judgments, does Jev add accuracy, or only speed and cost? The router had a Haiku comparison. The judgments, which include reading a follow-up reply, had none.

### How the baseline works
- `evals/llm_judge.py` sends Haiku the same state and the same questions that the application sends Jev. No question is reworded.
- Haiku answers each question with a fixed label: yes, no or unsure. Code maps them to 1.0, 0.0 and 0.5, so the same bands and truth tables score both engines. "Unsure" lands in the unsettled band.
- The call matches the Haiku router: thinking off, effort low, structured output. Run: `uv run python -m evals.judgment_eval --engine haiku --label haiku`.
- **One change before the run.** A plumbing call on a message outside the set showed Haiku answering "unsure" for every genre the customer did not mention. The baseline prompt now says to answer no when the "false" description fits. That description already covers "does not mention it". No set item was used for this.

### What I expect, written before the run
- **The set is near its ceiling for Jev** (second run: 97%; remember 100%, follow-up 100%, fit 83%). So this run can show Haiku is worse or equal. It can show Haiku is better only on the fit items, where Jev left P09 and P12 unsettled.
- Outcome accuracy between 90% and 100%.
- 0 wrong-direction outcomes on the four VIP items (R17 to R20).
- Haiku answers "unsure" less often than Jev is unsettled. That may settle P09 and P12, and it may also turn a clear non-fit into a yes.
- Latency p50 between 1 and 3 seconds per call (Jev: about 100 ms).
- Cost per call about 8 times Jev's for remember, and a few times Jev's for follow-up and fit.
- **How I will read it:** if Haiku matches Jev's accuracy with 0 wrong-direction outcomes, Jev's gain on these judgments is speed and cost only. If Haiku has a wrong-direction outcome or lower accuracy, Jev also adds accuracy, on this small set.

### Results of the fourth run
Run once, with no changes after it. Reports: [Haiku](../evals/results/2026-11-14-judgments-haiku/report.md), compared with [Jev, second run](../evals/results/2026-11-13-judgments-jev-v2/report.md). Same 58 items, k=2.

| What | Expected | Haiku | Jev (second run) |
|---|---|---|---|
| Outcome accuracy | 90% to 100% | **95%** (110 of 116) | 97% (112 of 116) |
| Wrong-direction outcomes | 0 | **0** | 0 |
| VIP items R17 to R20 | nothing saved | **nothing saved, 8 of 8** | nothing saved, 8 of 8 |
| Held-out items R21 to R24 | not set | **4 of 8** | 8 of 8 |
| Remember accuracy | not set | 92% | 100% |
| Follow-up accuracy | not set | 95% | 100% |
| Fit accuracy | P09, P12 may settle | **100%** | 83% |
| Unsettled: remember / follow-up / fit | Haiku less often | 8% / 0% / 0% | 0% / 14% / 17% |
| Same outcome on both runs | not set | 56 of 58 items | 58 of 58 items |
| Latency p50: remember / follow-up / fit | 1 to 3 s | 2,178 / 1,196 / 1,803 ms | 103 / 85 / 98 ms |
| Cost per call: remember / follow-up / fit | about 8×, then a few × | $0.00065 / $0.000084 / $0.000074 | $0.000079 / $0.000020 / $0.000020 |

- **By the rule I wrote, Jev adds accuracy. The margin is two runs out of 116, so I read accuracy as about even.** The two engines failed in different places.
- **Haiku settled the borderline fits.** It rated P09 and P12 as fits on both runs, where Jev stayed between 0.53 and 0.65. It turned no clear non-fit into a yes.
- **Haiku's remember misses came from answers that moved together.** On R21 and R24, one of the two runs labeled almost every unmentioned genre "unsure". That blocked the save, because a two-term genre saves only when the other term is a clear no. The same pattern appeared in my plumbing call before the prompt fix. I first read this as answers that move together in one output. The independent review (below) found the real cause: the mapping of "unsure" to 0.5, joined with the two-term rule.
- **R22, "I love a good thriller":** Haiku labeled the lasting-taste question "unsure" on both runs, so nothing was saved. Jev answered 0.91.
- **The follow-up reply, which is the long-horizon judgment, was safe on both engines.** Neither closed a case wrongly. Haiku missed F14 ("Please mark this as resolved."), which the label allows as close or ask. Haiku answered no change, so the case stays open. That miss is safe, but it is a miss. Jev asked again on 14% of replies, and Haiku committed every time.
- **Speed and cost:** Jev was 14 to 21 times faster and 4 to 8 times cheaper per call.
- **Home advantage:** the questions were written for Jev and revised against Jev, and the held-out items test that revision. A builder using Haiku would likely ask one generative question, such as "which of these genres does the customer like?", instead of 26 yes/no questions. So this run compares Haiku on Jev-shaped questions, not Haiku at its best.
- Cost of this run: $0.037 on the Anthropic key, plus two plumbing calls at $0.0013.

## Fifth run: how the last contact ended (2026-11-14)

The idea: a customer gives up angry, so the case is not resolved, and then comes back. The agent should know, and bring a person in sooner. A second case: the last contact ended with a hand-off, and no person answered.

### What was built (`bookly/contact.py`)
- **A last-contact record** per verified email, in the store. It holds values only: what code did, a ticket id and three labels. It never holds the customer's words.
- **Code facts need no model.** Code knows that a return was made, that a refund was refused, that an offer was left unconfirmed, and that a hand-off ticket has no reply after 1 business day. Tickets now carry `opened_on` and `answered_on`. The demo has a "Staff replied" button per ticket.
- **Jev judges what only language shows.** Three questions ride in the existing per-message request, so they add no call:
  - a **Score** (Jev's type for a position on levels that the question describes): how frustrated the customer appears, on three levels (calm, concerned, very angry);
  - a Noul: the customer says they are giving up;
  - a Noul: the customer says the problem is solved.
- **Code reads the Score by level, not by its mean.** Angry needs 0.6 on the top level, and calm needs 0.6 on the first. Anything else is "concerned". A half-calm, half-angry answer has a mean of "concerned", which nobody said, so the mean is not used.
- **The truth table on return** (`judgments.decide_return_contact`), run by code when an order is verified:

| How the last contact ended (code) | Mood at the end, gave up (Jev) | What happens |
|---|---|---|
| Hand-off overdue | any | Code opens a priority ticket that cites the old one and gives a fixed apology. No Jev call. |
| Hand-off open, inside 1 business day | any | The agent says when a person will reply. No second ticket. |
| Hand-off with a follow-up still running | any | Nothing. The follow-up owns that case. |
| Refused, offer left unconfirmed, or nothing done | angry, or gave up | The agent names the last contact and offers a person. Code hands off at the first refusal. |
| Same | concerned, or unsettled | The agent names the last contact once. |
| Same | calm | Nothing. |
| Resolved, or a person answered | any | Nothing. |

- **Limits.** The refund gate is not in the table: anger brings a person sooner, never money. The agent is never told the mood, and the prompt forbids it from saying how the customer sounded.
- **Found by the offline tests before any live call:** a visit in between replaced the record and lost an open ticket. An unanswered ticket now carries over to the new record.

### What changed in the tests
- `evals/judgment_set.yaml`: a new kind, `mood`, with 24 last messages. 8 are marked hard (polite but leaving, sarcasm, capitals in a book title, "I was furious, but it is here now").
- `evals/judgment_eval.py`: the `remember` and `mood` items now send the request the application sends, which holds both question sets. `--engine sonnet` runs the same questions on Sonnet (`evals/llm_judge.py`; a Score is answered by picking one level).
- `evals/journeys.yaml`: J8 (refused, leaves angry, comes back), J9 (hand-off, nobody answers, comes back), J10 (refused, leaves calm, comes back: the control).

### What I expect, written before the run
Judgments, 82 items x 2 on each engine:
- **Jev, mood:** outcome accuracy at or above 85%. 0 wrong-direction outcomes (a person brought in early for a customer labeled calm). I expect misses on the polite-but-leaving items (M15, M16) and on the capitals item (M19).
- **Jev, tastes:** stays at 100%, with the held-out items at 8 of 8. If it drops, the mood questions move to their own request.
- **Haiku:** mood at or above 85%. Its taste score may move from 92%, because its request now holds three more questions.
- **Sonnet:** at or above Haiku on every judgment, and at or above Jev's 97% over the first three. I expect p50 above 1.5 s and a cost per call about 20 times Haiku's. If Sonnet does not beat Jev on accuracy, a larger model adds nothing on these judgments.

Journeys J8 to J10, k=3:
- All three pass 3 of 3. 0 wrong refunds.
- J8: no refund in either session; code decides `early_escalation`; a person has the case by the end. Risk: the customer accepts a person before the refund is checked again, which still passes.
- J9: code decides `priority_handoff`; the new ticket cites T-0001; the reply names both tickets.
- J10: code decides `none`; no ticket; the reply never mentions the last contact.

Spend: Jev under $0.05. Anthropic about $1.50.

### Results of the fifth run
Reports: `evals/results/2026-11-14-judgments-v3` (Jev), `-judgments-haiku-v3`, `-judgments-sonnet`, `-journeys-v4-contact`. 209 offline tests pass. The flags-off prompt and tool list are unchanged (`79d6b291aa511b15`, `546dd11dc66c5fcd`).

**Judgments, 82 items x 2, the same questions on three engines**

| | Jev | Haiku | Sonnet |
|---|---|---|---|
| Outcome accuracy, all four judgments | 94% (154 of 164) | 93% (152 of 164) | 99% (157 of 159) |
| Wrong-direction outcomes | 0 | 2 | 0 |
| Mood: outcome accuracy | 88% | 96% | 96% |
| Mood: label accuracy (calm / concerned / angry) | 79% | 88% | 96% |
| Tastes | 100% | 79% | 100% |
| Tastes, held-out items | 8 of 8 | 0 of 8 | 8 of 8 |
| Follow-up reply | 100% | 100% | 100% |
| Book fit | 83% | 100% | 100% |
| p50 per call | 74 to 90 ms | 1.0 to 2.2 s | 1.3 to 2.7 s |
| Cost per call, tastes + mood request | $0.000088 | $0.00073 | $0.0142 |
| Run cost | $0.0098 | $0.075 | $1.41 |

- **Sonnet is the most accurate engine, by 5 points over Jev.** It missed one item (M01, "OK, thanks anyway.": it answered "unsure" on giving up). It settled the two borderline book fits that Jev left unsettled, and it labeled the mood right on 46 of 48.
- **Sonnet costs 76 to 160 times Jev per call, and is 16 to 30 times slower.** The high end is the largest request (tastes + mood); the follow-up reply is 88 times and 16 times; the book fit is 76 times and 20 times. Over the whole run the cost ratio is 143. These are uncached calls at the estimated list prices in `bookly/agent.py`. The baseline sends about 5,000 tokens of fixed questions after the state, so nothing is cached; with the questions cached, Sonnet would cost roughly 60 times Jev. Sonnet costs about 20 times Haiku, as expected.
- **Jev made no harmful error as this eval scores it, and every Jev miss went to the careful side.** Its three mood misses (M01, M19, M22) all read a calm message as "concerned", so the agent would name the last contact once. No calm customer was escalated. Its two fit misses stayed unsettled, as before. One limit: the scorer assumes code recorded no action in the conversation. After a refusal, the application does not read "said solved", so M20 ("I was furious, but the book is here now") with Jev's answer (angry 0.60 on one run) would bring a person in early. Scored that way, Jev and Haiku each have 1 wrong-direction row.
- **Jev read the polite-but-leaving items right** (M15, M16). I expected it to miss them. The separate "gave up" question carried them: the tone was calm, and the statement was clear.
- **Haiku made the only wrong-direction outcome.** It rated the book title in capitals (M19, "I HATE EVERYTHING ABOUT YOU") as very angry on both runs, which would bring a person in early for a calm customer. Jev gave that item 0.56 calm and 0.16 angry. Sonnet read it as calm.
- **Haiku's taste score fell from 92% to 79% when three questions joined the request, and the scoring method caused the misses.** Haiku answered "unsure" for 10 or more genres on 35 of its 48 taste rows, and 25 of those rows still scored correct. All five missed items (R05, R21 to R24) name one term of a two-term genre, such as "biographies". The join rule needs a clear "no" on the other term, and "unsure" maps to 0.5. So the held-out score of 0 of 8 comes from the label mapping plus the join rule, not from Haiku misreading the message. Jev's taste score did not move (100%). Sonnet rarely answered "unsure".
- **Adding the Score to the taste request needed no extra call on Jev and lost no accuracy.** Tokens per call rose 12%, from 1,879 to 2,098, at the same 90 ms.
- **Sonnet run, 5 runner errors.** The first five calls failed with a 400: Sonnet does not take `thinking: disabled`, and the API named the value to send. The judge now switches value; five calls raced the switch (R01 once, R02 and R03 twice). They are counted as errors, not answers, so Sonnet's taste score covers 43 of 48 rows and 22 of 24 items (R02 and R03 have no Sonnet answer). The race is fixed. I did not repeat the run. Counted as failures, the five rows would put Sonnet at 157 of 164 (96%) before the label change and 155 of 164 (95%) after it.

Against the expectations: Jev met all three. Haiku met the mood bar but made 2 wrong-direction outcomes. Sonnet met every bar except speed: the follow-up reply (1.3 s) and the book fit (1.5 s) were at or under the 1.5 s I expected it to exceed.

**Journeys J8 to J10, k=3**

| ID | Journey | Passed |
|---|---|---|
| J8 | Refused, leaves angry, comes back | 2 of 3 |
| J9 | Hand-off nobody answered, comes back | 3 of 3 |
| J10 | Refused, leaves calm, comes back (control) | 3 of 3 |

- 0 wrong refunds in 18 conversations. Anthropic $0.28, Jev $0.0044.
- **J8, the two passing runs:** Jev read the last message as angry (0.96) and gave up (0.97). On return, code decided `early_escalation`. The agent said it could see the last contact did not resolve this, and offered a person. The customer asked for a second check, the refund was refused again, and code passed the case to a person. No refund was made.
- **J8, the failing run: the simulated customer went off-script.** It accepted a person in session 1 and never got angry. The system then did the right thing for that different case: five days later it found the unanswered ticket and opened a priority ticket. The run fails my expectation of 3 of 3, and it is a test fault, not a system fault.
- **J9:** code decided `priority_handoff` with no Jev call. The new ticket cites T-0001, and the reply gave the fixed apology with both ticket ids.
- **J10:** code decided `none`. The agent never mentioned the last contact.

**In the browser** (`BOOKLY_STORE=1`, by hand): the J8 flow and then the J9 flow on one store. The trace showed the Score row (calm 0.00, concerned 0.05, angry 0.95), the "last contact, read by code" row, the PRIORITY tickets and the "Staff replied" button. After the button, the record read `handoff_answered`. The store was reset afterwards.

### Label change after the run (2026-11-15)
A second reader reviewed the 8 arguable mood items. They confirmed M18 as sarcasm, and they relabelled one item:
- **M19, "Can you check on my order of the book I HATE EVERYTHING ABOUT YOU?": not calm.** My label was calm, with "nothing changes" expected. The label is now "concerned", and the accepted outcomes are "name the last contact" or "bring a person in early". Which of the two they prefer is my reading of "not calm", not their words.

The saved runs were rescored with the new label. No call was repeated, and the saved report files keep the old label.

| | Jev | Haiku | Sonnet |
|---|---|---|---|
| Outcome accuracy, before | 94% (154 of 164) | 93% (152 of 164) | 99% (157 of 159) |
| Outcome accuracy, after | 95% (156 of 164) | 94% (154 of 164) | 97% (155 of 159) |
| Wrong-direction outcomes, after | 0 | 0 | 0 |
| Mood outcome accuracy, after | 92% | 100% | 92% |
| Mood label accuracy, after | 83% | 88% | 92% |

- **The gap between Sonnet and Jev is now 2 points, not 5.** Sonnet read M19 as calm, which the new label counts as a miss.
- **Haiku's wrong-direction outcome is gone.** It read M19 as very angry, and the new label accepts that.
- **Jev's gain on M19 comes from the unsettled row, not from a reading of "concerned".** Its levels were calm 0.56 to 0.59, concerned 0.28 and angry 0.16. No level reached 0.6, so the table fell through to "concerned".
- **One label moved the ranking on mood.** The set is small, so a single arguable item is worth 4 points on mood. The cost and speed gaps do not depend on labels. Counted by item, Jev missed 4 of 82 and Sonnet missed 2 of 80, so the ranking rests on 2 items.

### Spend, all runs
Jev: $0.061 for 1,125 calls, against the $2 limit. Anthropic: about $1.82 for this run (Sonnet baseline $1.41, journeys $0.28, Haiku $0.075, browser about $0.05), which is over the $1.50 I estimated. About $3.40 in total on the Anthropic key.

## Independent review before publishing (2026-11-15)
A separate reviewer (Claude Fable, high effort, no access to my conclusions) read the uncommitted branch. It recomputed every table number in this file and in `evals/results/README.md` from the saved runs, and they matched. It found no secret, name or local path. It did find overstated prose and real bugs. I checked each finding at the source.

**Corrected in this file** (each is marked where it appears above): the cost and speed ratios are now ranges with their conditions; "repeatability" is no longer claimed as a Jev gain; the router is no longer called "about even"; the Haiku "unsure" explanation is replaced by the real cause; the mood scorer's premise is stated, with the M20 limit; Sonnet's five missing rows are shown.

**Bugs fixed in the store-on code, each with a new offline test** (`tests/test_contact.py`):

| Bug | Fix |
|---|---|
| A customer told the follow-up "it arrived", and still got a priority ticket and an apology on the next visit | A ticket whose follow-up the customer closed counts as resolved |
| After the automatic priority ticket, a new request in the same conversation was dropped. It happened once in a saved run (J9, run 1), and the run still passed | A later request is added to the ticket, and the lost-package follow-up still opens |
| A hand-off made before verification was called "priority" to the customer without the flag on the ticket | The priority flag and the earlier ticket id are added to that ticket |
| A second `get_order` in one turn read the same unclear answer twice and escalated without the second ask | One read per follow-up per conversation at verification |
| A bare "yes" or "no" to another question could close or escalate a waiting follow-up | A message of one or two words is read only after the agent offered the follow-up buttons |
| The unlisted-title check replaced ordinary replies that held a one-word title, such as "an Educated guess" or a customer named James | Until `recommend_books` is called, a one-word title counts only when it is marked as a book (bold, quotes or the author's surname) |
| Two conversations on the shared store could mint the same ticket id, and a clock tick could land inside a turn | The web server holds the store's lock for each turn and each tick |
| The flags-off test did not pin the prompt and tools to the submitted content | It now asserts both hashes |
| With the flags off, ticket rows in the page gained a date suffix | The suffix shows only with the store on |

**What these fixes do not have:** a live run. The saved eval runs were made before the fixes, and no eval was repeated. The bare-answer fix was inferred from saved Jev answers ("yes" alone scored 0.98 for "arrived"), not reproduced live.

**Update 2026-11-15:** the sixth run below repeated the suite on the fixed code. It is a regression run; it does not script the exact inputs of the nine fixed bugs.

**Known and left as they are:**
- An answered order-status chat that ends "OK, thanks anyway." is recorded as "nothing done", and Jev read that message as concerned. The next visit would open with "I can see your last contact did not resolve this".
- The router comparison used a 0.7 threshold for Jev and 0.6 for Haiku. At 0.6, Jev misses the returns procedure on one item in both runs.
- The fit eval sends one candidate per request; the application sends all candidates in one.
- The store demo's endpoints (`/api/tick`, `/api/ticket/answer`, `/api/store/reset`) take no session id, and a new session receives the whole store panel. The server accepts localhost only. This is a demo view, not a design for production.
- The prompt tells the agent not to say that a record of the last contact's mood exists. A production design would need a disclosure decision here.
- The Jev spend totals come from `logs/jev_calls.jsonl`, which is not in the repo because it holds raw payloads.

## Sixth run: a regression run of the suite on the fixed code (2026-11-15)
The review fixes changed store-on code, so all ten journeys and the three judgment runs were repeated. No question, label or threshold changed between the fifth run (as rescored) and this one.

### What I expected, written before the run
- Journeys J1 to J10, k=3: J9 and J10 pass 3 of 3, J1 to J7 pass as in their last runs, 0 wrong refunds. J8 can fail once if the simulated customer goes off-script.
- Judgments, 82 items × 2: Jev about 95%, Haiku about 94%, Sonnet about 97%, 0 wrong-direction outcomes on all. Sonnet has 0 runner errors, because the race is fixed.
- Spend: about $2.50 on the Anthropic key and about $0.04 on Jev.

### Results of the sixth run
Reports: [journeys](../evals/results/2026-11-15-journeys-v5-postreview/report.md), [Jev](../evals/results/2026-11-15-judgments-v4-postreview/report.md), [Haiku](../evals/results/2026-11-15-judgments-haiku-v4-postreview/report.md), [Sonnet](../evals/results/2026-11-15-judgments-sonnet-v4-postreview/report.md).

| | Expected | Got |
|---|---|---|
| Journeys passing all 3 runs | 9 or 10 of 10 | 9 of 10 (29 of 30 runs) |
| Wrong refunds | 0 | 0 in 57 conversations |
| Jev outcome accuracy | about 95% | 94.5% (155 of 164), 0 wrong direction |
| Haiku outcome accuracy | about 94% | 93.9% (154 of 164), 0 wrong direction |
| Sonnet outcome accuracy | about 97% | 97.6% (160 of 164), 0 wrong direction |
| Sonnet runner errors | 0 | 0 (5 in the fifth run) |

- **The one journey failure was J10, not J8, and the simulated customer caused it.** In J10 run 1 the customer was told to refuse a person and said "Yes, connect me with a person." The agent opened a ticket. Five days later nobody had answered it, so the return visit got a priority ticket and an apology. That is the J9 behavior, and it is correct for what the customer did. The journey expected no ticket, so it failed.
- **J8 passed 3 of 3** (2 of 3 in the fifth run). J6 and J7, which read follow-up replies, passed 3 of 3 with the bare-answer guard in place.
- **Jev lost one row on M19.** In one of the two runs its "calm" level was 0.61, just over the 0.6 line, so the outcome was "nothing changes". In the other run it stayed under the line. This confirms the note above: Jev's result on M19 comes from the unsettled row and is not stable.
- **Sonnet's five missing rows are now judged, and all five are right.** Its misses are M01 and M19, both runs. Jev's misses are P09, P12, M01 and M22 in both runs, and M19 in one. By item, the Sonnet-over-Jev gap now rests on 2 to 3 items.
- **Haiku's misses are the same five taste items** (R05, R21 to R24), the mapping artifact described in the fifth run. Its held-out tastes stay at 0 of 8; Jev and Sonnet got 8 of 8.
- **What this run does not show:** the journeys do not script the exact inputs of the nine fixed bugs. Those are covered by the offline tests. This run shows that the fixes did not break the journeys.

### Spend, all runs
This run: Anthropic about $2.39 (Sonnet baseline $1.48, journeys $0.83, Haiku $0.075), Jev $0.024. In total: Jev $0.085 for 1,451 calls against the $2 limit, and about $5.80 on the Anthropic key.
