# Model comparison: Sonnet 5.5 vs Opus 5.5

The same 16 scenarios, each run 5 times, at the same effort (`low`), with the same simulated customer.

| | Sonnet 5.5 (shipped) | Opus 5.5 |
|---|---|---|
| Scenarios passing all 5 runs | 16 / 16 | 15 / 16 |
| Wrong refunds | 0 / 80 | 0 / 80 |
| Cost per conversation (estimated at list prices, agent only) | $0.013 | $0.025 |
| Turn latency p50 / p95 | 4.2 s / 8.7 s | 5.1 s / 12.8 s |

**Opus's one failure was real.** In one P2 run, it handed off after the customer said "no thanks", with the summary set to "placeholder", and then apologized. The payload check caught it ([report](../evals/results/2026-10-13-opus-k5/report.md)).

**How to read this.** Sonnet already scored 16 of 16, so the suite has no headroom for a bigger model to show a gain. The intervals overlap. Eighty conversations do not rank the models in general. They show that on this design the cheaper, faster model is enough, because the rules that matter run in code.

**Fairness.** Opus 5.5 defaults to a different effort level than Sonnet 5.5, so both runs set `effort: low` explicitly.

**Reproduce:** `uv run python -m evals.run_evals --k 5 --model claude-opus-5-5 --effort low --label opus`.
