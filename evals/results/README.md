# Eval runs

Each folder holds `report.md` (read this first), `summary.json` and `transcripts.jsonl` (every conversation, with the full trace).

| Folder | What it is | Result |
|---|---|---|
| `2026-10-13-sonnet-k5-v2` | **The headline run.** Claude Sonnet 5.5, effort low, k=5 | 16/16 pass^5, 0 wrong refunds in 80 |
| `2026-10-13-window14` | **Change test.** Same suite, return window cut from 30 to 14 days in `policy.yaml` | R10 and R8 moved, as predicted; 16/16 pass^5 |
| `2026-10-13-opus-k5` | **Model comparison.** Claude Opus 5.5, same effort, k=5 | 15/16 pass^5 (one real error), 0 wrong refunds, 2x cost |
| `2026-10-13-sonnet-k5` | History: the first k=5 run, before the claim-check fix | 15/16; R8 failed on a false block by the claim check |
| `2026-10-13-smoke` | History: the first k=1 run, before the P1 scenario fix | 15/16; P1's simulated customer went off-script |

The three runs at the top were re-graded with the final rubric (`evals/rescore.py`). The two history runs keep the rubric they ran with, so they show what the evals caught.

The reported runs were made before two later gate fixes (no weak acknowledgements in the allowlist; the Confirm button bound to its card's quote). Neither fix touches a path the runs used. See `docs/BUILD_LOG.md`.
