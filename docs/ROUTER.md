# Intent router

Added after the take-home review on 2026-10-27, where the panel asked how intent detection works today and at about fifty intents, and how one message with several requests is routed. Off by default (`BOOKLY_ROUTER=1` turns it on). The submitted version is tagged `submitted-2026-10-22`.

## What I expect, written before the first run (2026-10-29)
- **The needed procedure is loaded in at least 95% of classifications**, at the chosen threshold, with **zero misses of the returns procedure**. Loading a procedure too many costs context; missing one can change what the agent does, so misses are the number that matters.
- Exact label match of at least 85%. I expect the vague openers and the short follow-ups to be the hardest.
- Fallback to all procedures in no more than 10% of classifications. More than that, and the router saves little.
- Latency p50 under 1.5 s, and cost under $0.0002 per call. The two smoke-test calls took 1.2 s and 2.4 s, at about 650 input and 20 output tokens.
- If the needed procedure is loaded in under 95% of classifications, the router stays off, and this page says why.

## Results
_Pending the first run of `uv run python -m evals.router_eval --k 3`._
