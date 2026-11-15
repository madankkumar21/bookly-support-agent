# Intent router eval: jev-v2-holdout

Model `jev-1.14.0`, k=3, threshold 0.7, 12 items from evals/router_holdout.yaml (synthetic), run 2026-11-13T12:47:11.

## Headline
- **Needed procedure loaded in 33 of the 33 classifications that needed one** (0 misses; 0 missed the returns procedure; 3 of 36 needed none, because the message was out of scope).
- Exact label match 94%. Fallback to all procedures 8%. Loaded more than needed 0%.
- Same answer on all 3 runs: 11/12 items. Router errors: 0.
- Latency p50 113 ms, p95 205 ms. Cost $0.000037 per call, $0.0013 in total.

## By kind
| Kind | Runs | Exact | Needed procedure loaded |
|---|---|---|---|
| multi | 15 | 100% | 100% |
| out_of_scope | 3 | 100% | none needed |
| single | 18 | 89% | 100% |

## Recall per intent
| Intent | Runs that needed it | Recall |
|---|---|---|
| order_status | 9 | 100% |
| returns | 12 | 100% |
| policy | 24 | 100% |
| other | 6 | 100% |

## Threshold sweep (choose the threshold from this table)
| Threshold | Needed procedure loaded | Fallback to all | Missed returns |
|---|---|---|---|
| 0.0 | 100% | 0% | 0 |
| 0.5 | 100% | 0% | 0 |
| 0.6 | 100% | 8% | 0 |
| 0.7 | 100% | 8% | 0 |
| 0.8 | 100% | 25% | 0 |
| 0.9 | 100% | 44% | 0 |

## Exact match by stated confidence
| Confidence | Runs | Exact |
|---|---|---|
| 0.0-0.6 | 3 | 33% |
| 0.6-0.8 | 6 | 100% |
| 0.8-0.9 | 7 | 100% |
| 0.9-1.0 | 20 | 100% |

## Single-intent items: expected label → predicted labels
- **order_status**: order_status ×3
- **other**: other ×3
- **returns**: returns ×6
- **policy**: policy ×7, policy,returns ×2

## Misses (a needed procedure was not loaded)
- None.

Items with any inexact run: H7.
