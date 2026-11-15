# Intent router eval: haiku-holdout

Model `claude-haiku-5-5`, k=3, threshold 0.6, 12 items from evals/router_holdout.yaml (synthetic), run 2026-11-13T12:47:20.

## Headline
- **Needed procedure loaded in 33 of the 33 classifications that needed one** (0 misses; 0 missed the returns procedure; 3 of 36 needed none, because the message was out of scope).
- Exact label match 92%. Fallback to all procedures 0%. Loaded more than needed 8%.
- Same answer on all 3 runs: 12/12 items. Router errors: 0.
- Latency p50 1091 ms, p95 1423 ms. Cost $0.000076 per call, $0.0027 in total.

## By kind
| Kind | Runs | Exact | Needed procedure loaded |
|---|---|---|---|
| multi | 15 | 100% | 100% |
| out_of_scope | 3 | 100% | none needed |
| single | 18 | 83% | 100% |

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
| 0.6 | 100% | 0% | 0 |
| 0.7 | 100% | 0% | 0 |
| 0.8 | 100% | 0% | 0 |
| 0.9 | 100% | 17% | 0 |

## Exact match by stated confidence
| Confidence | Runs | Exact |
|---|---|---|
| 0.0-0.6 | 0 |  |
| 0.6-0.8 | 0 |  |
| 0.8-0.9 | 6 | 50% |
| 0.9-1.0 | 30 | 100% |

## Single-intent items: expected label → predicted labels
- **order_status**: order_status ×3
- **other**: other ×3
- **returns**: order_status,returns ×3, returns ×3
- **policy**: policy ×9

## Misses (a needed procedure was not loaded)
- None.

Items with any inexact run: H12.
