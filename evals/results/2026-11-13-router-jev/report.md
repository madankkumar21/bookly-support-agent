# Intent router eval: jev

Model `jev-1.14.0`, k=3, threshold 0.7, 60 items from evals/router_set.yaml (synthetic), run 2026-11-13T11:30:49.

## Headline
- **Needed procedure loaded in 156 of the 159 classifications that needed one** (3 misses; 0 missed the returns procedure; 21 of 180 needed none, because the message was out of scope).
- Exact label match 87%. Fallback to all procedures 23%. Loaded more than needed 0%.
- Same answer on all 3 runs: 58/60 items. Router errors: 0.
- Latency p50 91 ms, p95 163 ms. Cost $0.000032 per call, $0.0057 in total.

## By kind
| Kind | Runs | Exact | Needed procedure loaded |
|---|---|---|---|
| followup | 30 | 57% | 100% |
| injection | 12 | 100% | 100% |
| multi | 24 | 75% | 88% |
| out_of_scope | 18 | 100% | none needed |
| single | 84 | 98% | 100% |
| vague | 12 | 75% | 100% |

## Recall per intent
| Intent | Runs that needed it | Recall |
|---|---|---|
| order_status | 54 | 100% |
| returns | 75 | 96% |
| policy | 45 | 80% |
| other | 27 | 100% |

## Threshold sweep (choose the threshold from this table)
| Threshold | Needed procedure loaded | Fallback to all | Missed returns |
|---|---|---|---|
| 0.0 | 92% | 0% | 3 |
| 0.5 | 92% | 0% | 3 |
| 0.6 | 95% | 13% | 3 |
| 0.7 | 98% | 23% | 0 |
| 0.8 | 98% | 33% | 0 |
| 0.9 | 100% | 50% | 0 |

## Exact match by stated confidence
| Confidence | Runs | Exact |
|---|---|---|
| 0.0-0.6 | 24 | 50% |
| 0.6-0.8 | 36 | 75% |
| 0.8-0.9 | 30 | 90% |
| 0.9-1.0 | 90 | 100% |

## Single-intent items: expected label → predicted labels
- **returns**: returns ×50, order_status,returns ×7, other ×3
- **order_status**: order_status ×39, order_status,returns ×3
- **policy**: policy ×31, returns ×3, policy,returns ×2
- **other**: other ×21

## Misses (a needed procedure was not loaded)
- M5#0: "Can you refund the wrong book you sent and tell me if you ship to the UK?" expected ['returns', 'policy'], got ['returns'] at 0.88
- M5#1: "Can you refund the wrong book you sent and tell me if you ship to the UK?" expected ['returns', 'policy'], got ['returns'] at 0.87
- M5#2: "Can you refund the wrong book you sent and tell me if you ship to the UK?" expected ['returns', 'policy'], got ['returns'] at 0.88

Items with any inexact run: F1, F3, F4, F7, F8, M2, M5, P8, V2.
