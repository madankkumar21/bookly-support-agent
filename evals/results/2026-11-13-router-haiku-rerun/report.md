# Intent router eval: haiku-rerun

Model `claude-haiku-5-5`, k=3, threshold 0.6, 60 items from evals/router_set.yaml (synthetic), run 2026-11-13T11:31:40.

## Headline
- **Needed procedure loaded in 159 of the 159 classifications that needed one** (0 misses; 0 missed the returns procedure; 21 of 180 needed none, because the message was out of scope).
- Exact label match 95%. Fallback to all procedures 2%. Loaded more than needed 3%.
- Same answer on all 3 runs: 58/60 items. Router errors: 0.
- Latency p50 1076 ms, p95 1694 ms. Cost $0.000075 per call, $0.0135 in total.

## By kind
| Kind | Runs | Exact | Needed procedure loaded |
|---|---|---|---|
| followup | 30 | 87% | 100% |
| injection | 12 | 100% | 100% |
| multi | 24 | 100% | 100% |
| out_of_scope | 18 | 100% | none needed |
| single | 84 | 98% | 100% |
| vague | 12 | 75% | 100% |

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
| 0.8 | 100% | 4% | 0 |
| 0.9 | 100% | 8% | 0 |

## Exact match by stated confidence
| Confidence | Runs | Exact |
|---|---|---|
| 0.0-0.6 | 3 | 0% |
| 0.6-0.8 | 5 | 100% |
| 0.8-0.9 | 6 | 83% |
| 0.9-1.0 | 166 | 97% |

## Single-intent items: expected label → predicted labels
- **returns**: returns ×57, order_status,returns ×3
- **order_status**: order_status ×39, order_status,returns ×2, order_status,policy ×1
- **policy**: policy ×33, policy,returns ×3
- **other**: other ×21

## Misses (a needed procedure was not loaded)
- None.

Items with any inexact run: F10, F8, O3, V2.
