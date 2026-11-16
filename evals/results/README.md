# Eval runs

Each folder holds `report.md` (read this first), `summary.json` and `transcripts.jsonl` (every conversation, with the full trace).

| Folder | What it is | Result |
|---|---|---|
| `2026-10-13-sonnet-k5-v2` | **The headline run.** Claude Sonnet 5.5, effort low, k=5 | 16/16 pass^5, 0 wrong refunds in 80 |
| `2026-10-13-window14` | **Change test.** Same suite, change-of-mind return window cut from 30 to 14 days in `policy.yaml` | R10 and R8 changed outcome, as predicted; 16/16 pass^5 |
| `2026-10-13-opus-k5` | **Model comparison.** Claude Opus 5.5, same effort, k=5 | 15/16 pass^5 (one real error), 0 wrong refunds, 2x cost |
| `2026-10-29-router-haiku` | **Intent router on its own** (added after the review). 60 synthetic labelled messages × 3 | Needed procedure loaded 159/159 (21 needed none); 94% exact |
| `2026-10-29-sonnet-k5-routeron` | **Router in the agent.** Same suite, router on, k=5 | 16/16 pass^5, 0 wrong refunds; p50 3.5 s |
| `2026-10-29-sonnet-k5-routeroff` | **Same-day baseline**, router off, k=5 | 15/16 (P1: the simulated customer went off-script), 0 wrong refunds; p50 2.7 s |
| `2026-11-13-router-jev` | **The router on Jev** (learning build, `docs/JEV.md`). The same 60 items × 3 | Needed procedure loaded 156/159; 87% exact; 23% fall-back; p50 91 ms |
| `2026-11-13-router-haiku-rerun` | **Same-day Haiku baseline** for the Jev router | 159/159; 95% exact; p50 1,076 ms |
| `2026-11-13-judgments-jev` | **Jev judgments on their own.** 54 labelled items × 2, scored through the truth tables | 94% outcome accuracy; 0 wrong-direction outcomes |
| `2026-11-13-journeys` | **Multi-session journeys**, store on, k=3 | 6/7 pass all runs (20/21); 0 wrong refunds in 39 conversations |
| `2026-11-13-router-jev-v2` | **Second run, after three fixes** (`docs/JEV.md`). The policy intent as two questions, original 60 × 3 | 159/159; 87% exact; 18% fall-back |
| `2026-11-13-router-jev-v2-holdout` | The same wording on 12 held-out items it was not written for | 33/33; 94% exact |
| `2026-11-13-router-haiku-holdout` | Haiku on the same 12 held-out items | 33/33; 92% exact |
| `2026-11-13-judgments-jev-v2` | Second run: one question per genre term; 4 held-out items added | 97% outcome accuracy; 0 wrong direction; held-out 8/8 |
| `2026-11-13-journeys-v2` | Second run: picks carry catalog facts | 6/7 pass all runs (20/21); 0 wrong refunds in 39. Its Jev spend line also counts two evals that ran at the same time |
| `2026-11-14-judgments-haiku` | Fourth run: the same 58 judgment items on Haiku, with yes/no/unsure labels scored through Jev's truth tables (`evals/llm_judge.py`) | 95% (Jev 97%); 0 wrong direction; held-out 4/8 (Jev 8/8); fit 100% (Jev 83%); p50 1.2 to 2.2 s (Jev about 0.1 s) |
| `2026-11-14-judgments-v3` | Fifth run: 82 items (24 new `mood` items); the taste request now also carries the mood Score and two Nouls | 94%; 0 wrong direction; mood 88%; tastes 100%; held-out 8/8 |
| `2026-11-14-judgments-haiku-v3` | The same 82 items on Haiku | 93%; 2 wrong direction (a book title in capitals read as angry); tastes 79%; held-out 0/8 |
| `2026-11-14-judgments-sonnet` | The same 82 items on Sonnet | 99% of 159 judged (5 runner errors on 3 taste items); 0 wrong direction; 76x to 160x Jev's cost per call, uncached |
| `2026-11-14-journeys-v4-contact` | Journeys J8 to J10: how the last contact ended (`bookly/contact.py`), k=3 | J9 and J10 3/3; J8 2/3 (the simulated customer went off-script once); 0 wrong refunds in 18 |
| `2026-11-15-journeys-v5-postreview` | Sixth run, after the review fixes: all ten journeys, k=3 | 9/10 pass all runs (29/30); J10 failed once (the simulated customer asked for a person against its script); 0 wrong refunds in 57 |
| `2026-11-15-judgments-v4-postreview` | Sixth run: the 82 items on Jev, with the M19 relabel | 94.5% (155/164); 0 wrong direction; held-out 8/8 |
| `2026-11-15-judgments-haiku-v4-postreview` | The same on Haiku | 93.9% (154/164); 0 wrong direction; held-out 0/8 |
| `2026-11-15-judgments-sonnet-v4-postreview` | The same on Sonnet, with the runner race fixed | 97.6% (160/164); 0 wrong direction; 0 runner errors |
| `2026-11-13-journeys-v3-j1` | Third run, J1 only: the agent recommends only when asked; the simulated customer no longer tries to buy | 1/1 passes all runs (3/3); 0 wrong refunds in 6 conversations |
| `2026-11-13-journeys-smoke` | History: one journey, k=1, to check the new runner before the full run | 1/1 |
| `2026-10-13-sonnet-k5` | History: the first k=5 run, before the claim-check fix | 15/16; R8 failed on a false block by the claim check |
| `2026-10-13-smoke` | History: the first k=1 run, before the P1 scenario fix | 15/16; P1's simulated customer went off-script |

The three `2026-11-14-judgments-*` fifth-run folders keep the label M19 had when they ran. It was relabelled on 2026-11-15; the rescored numbers (Jev 95%, Haiku 94%, Sonnet 97%, 0 wrong direction on all) are in `docs/JEV.md`.

The three runs at the top were re-graded with the final rubric (`evals/rescore.py`). The two history runs keep the rubric they ran with, so they show what the evals caught.

The reported runs were made before two later gate fixes (no weak acknowledgements in the allowlist; the Confirm button bound to its card's quote). Neither fix touches a path the runs used. See `docs/BUILD_LOG.md`.
