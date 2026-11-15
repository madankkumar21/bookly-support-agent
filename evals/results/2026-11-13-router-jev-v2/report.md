# Intent router eval: jev-v2

Model `jev-1.14.0`, k=3, threshold 0.7, 60 items from evals/router_set.yaml (synthetic), run 2026-11-13T12:47:10.

## Headline
- **Needed procedure loaded in 159 of the 159 classifications that needed one** (0 misses; 0 missed the returns procedure; 21 of 180 needed none, because the message was out of scope).
- Exact label match 87%. Fallback to all procedures 18%. Loaded more than needed 2%.
- Same answer on all 3 runs: 59/60 items. Router errors: 0.
- Latency p50 92 ms, p95 172 ms. Cost $0.000037 per call, $0.0067 in total.

## By kind
| Kind | Runs | Exact | Needed procedure loaded |
|---|---|---|---|
| followup | 30 | 50% | 100% |
| injection | 12 | 100% | 100% |
| multi | 24 | 88% | 100% |
| out_of_scope | 18 | 100% | none needed |
| single | 84 | 98% | 100% |
| vague | 12 | 75% | 100% |

## Recall per intent
| Intent | Runs that needed it | Recall |
|---|---|---|
| order_status | 54 | 100% |
| returns | 75 | 96% |
| policy | 45 | 100% |
| other | 27 | 100% |

## Threshold sweep (choose the threshold from this table)
| Threshold | Needed procedure loaded | Fallback to all | Missed returns |
|---|---|---|---|
| 0.0 | 98% | 0% | 3 |
| 0.5 | 98% | 0% | 3 |
| 0.6 | 98% | 8% | 3 |
| 0.7 | 100% | 18% | 0 |
| 0.8 | 100% | 30% | 0 |
| 0.9 | 100% | 44% | 0 |

## Exact match by stated confidence
| Confidence | Runs | Exact |
|---|---|---|
| 0.0-0.6 | 15 | 27% |
| 0.6-0.8 | 39 | 69% |
| 0.8-0.9 | 25 | 100% |
| 0.9-1.0 | 101 | 100% |

## Single-intent items: expected label → predicted labels
- **returns**: returns ×48, order_status,returns ×9, other ×3
- **order_status**: order_status ×39, order_status,returns ×3
- **policy**: policy ×31, policy,returns ×5
- **other**: other ×21

## Misses (a needed procedure was not loaded)
- None.

Items with any inexact run: F1, F3, F4, F7, F8, M2, P8, V2.
