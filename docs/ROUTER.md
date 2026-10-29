# Intent router

Added after the take-home review on 2026-10-27, where the panel asked how intent detection works today and at about fifty intents, and how one message with several requests is routed. Off by default (`BOOKLY_ROUTER=1` turns it on). The submitted version is tagged `submitted-2026-10-22`.

## What I expect, written before the first run (2026-10-29)
- **The needed procedure is loaded in at least 95% of classifications**, at the chosen threshold, with **zero misses of the returns procedure**. Loading a procedure too many costs context; missing one can change what the agent does, so misses are the number that matters.
- Exact label match of at least 85%. I expect the vague openers and the short follow-ups to be the hardest.
- Fallback to all procedures in no more than 10% of classifications. More than that, and the router saves little.
- Latency p50 under 1.5 s, and cost under $0.0002 per call. The two smoke-test calls took 1.2 s and 2.4 s, at about 650 input and 20 output tokens.
- If the needed procedure is loaded in under 95% of classifications, the router stays off, and this page says why.

## Results: the router on its own (2026-10-29, first run, no prompt changes after it)
60 synthetic items × 3 runs = 180 classifications, Haiku 5.5, threshold 0.6. Full report: [evals/results/2026-10-29-router-haiku/report.md](../evals/results/2026-10-29-router-haiku/report.md).

| What | Expected | Measured |
|---|---|---|
| Needed procedure loaded | ≥ 95% | **100%** (0 misses) |
| Missed the returns procedure | 0 | **0** |
| Exact label match | ≥ 85% | 94% |
| Fallback to all procedures | ≤ 10% | 2% |
| Latency p50 / p95 | < 1.5 s | 1.0 s / 1.8 s |
| Cost per call | < $0.0002 | $0.000075 |

- **Every inexact answer erred wide.** All 10 inexact runs (four items) added a procedure, and none dropped one. Returns was added to a return-window question after a delivery (F8) and to "delivered but I never got it" (O3). Order status was added to two vague openers (V1, V2). An extra returns procedure costs context, not safety: the gate still refuses any refund without a confirmed quote.
- **The vague openers are the weak spot**, at 50% exact. "My order is messed up" usually gets order status and returns, at lower confidence (0.45–0.6). That's the safe direction, because both procedures get loaded.
- **All 8 multi-request items were exact**, including the review's own example (a damaged return plus a recommendation → returns and other). So were all 4 injection attempts.
- **The threshold stays at 0.6.** Coverage was 100% at every threshold from 0.0 to 0.9. Raising the threshold only raises fallback (from 2% to 7%), and stated confidence below 0.8 matched exactly in only 3 of 9 runs.

**Caveats**
- The set is synthetic, and the same person wrote the router prompt and the labels. The number proves the method, not Bookly's real accuracy. On a real deployment, the labelled set comes from the customer's own tickets, labelled by their team.
- A router call adds about a second to most turns. At three intents that buys nothing, which is why the router is off by default. The case for turning it on starts at dozens of procedures.
