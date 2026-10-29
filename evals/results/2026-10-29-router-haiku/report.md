# Intent router eval: haiku

Model `claude-haiku-5-5`, k=3, threshold 0.6, 60 items from evals/router_set.yaml (synthetic), run 2026-10-29T01:08:10.

## Headline
- **Needed procedure loaded in 100% of 180 classifications** (0 misses; 0 missed the returns procedure).
- Exact label match 94%. Fallback to all procedures 2%. Loaded more than needed 4%.
- Same answer on all 3 runs: 59/60 items. Router errors: 0.
- Latency p50 1024 ms, p95 1827 ms. Cost $0.000075 per call, $0.0135 in total.

## By kind
| Kind | Runs | Exact | Needed procedure loaded |
|---|---|---|---|
| followup | 30 | 90% | 100% |
| injection | 12 | 100% | 100% |
| multi | 24 | 100% | 100% |
| out_of_scope | 18 | 100% | 100% |
| single | 84 | 99% | 100% |
| vague | 12 | 50% | 100% |

## Recall per intent
| Intent | Runs that needed it | Recall |
|---|---|---|
| order_status | 54 | 100% |
| returns | 75 | 100% |
| policy | 45 | 100% |
| other | 27 | 100% |

## Threshold sweep (choose the threshold from this table)
| Threshold | Needed procedure loaded | Fallback to all | Missed returns |
|---|---|---|---|
| 0.0 | 100% | 0% | 0 |
| 0.5 | 100% | 1% | 0 |
| 0.6 | 100% | 2% | 0 |
| 0.7 | 100% | 3% | 0 |
| 0.8 | 100% | 5% | 0 |
| 0.9 | 100% | 7% | 0 |

## Exact match by stated confidence
| Confidence | Runs | Exact |
|---|---|---|
| 0.0-0.6 | 3 | 0% |
| 0.6-0.8 | 6 | 50% |
| 0.8-0.9 | 4 | 100% |
| 0.9-1.0 | 167 | 98% |

## Single-intent items: expected label → predicted labels
- **returns**: returns ×54, order_status,returns ×6
- **order_status**: order_status ×41, order_status,returns ×1
- **policy**: policy ×33, policy,returns ×3
- **other**: other ×21

## Misses (a needed procedure was not loaded)
- None.

Items with any inexact run: F8, O3, V1, V2.
