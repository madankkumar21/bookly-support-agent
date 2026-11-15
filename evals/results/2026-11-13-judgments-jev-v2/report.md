# Jev judgments eval: jev-v2

Model `jev-1.14.0`, k=2, evals/judgment_set.yaml (synthetic), bands yes ≥ 0.7, no ≤ 0.3, close ≥ 0.85, run 2026-11-13T12:47:32.

## Headline
- **Outcome accuracy 97%** over 116 judged items (each scored through its truth table). Errors: 0.
- **Wrong-direction outcomes: 0** (a taste saved from a special-treatment message, a follow-up closed without the customer saying it arrived, or a clear non-fit rated yes).
- Held-out items (added after a wording change, never used to word a question): 8 of 8 correct.
- Jev spend $0.005136.

## By judgment
| Judgment | Runs | Accuracy | Accuracy, clear items | Wrong direction | Unsettled | Same outcome every run | p50 | Tokens/call | Cost/call |
|---|---|---|---|---|---|---|---|---|---|
| remember | 48 | 100% | 100% | 0 | 0% | 24/24 | 103 ms | 1879 | $0.000079 |
| follow_up | 44 | 100% | 100% | 0 | 14% | 22/22 | 85 ms | 469 | $0.000020 |
| fit | 24 | 83% | 91% | 0 | 17% | 12/12 | 98 ms | 476 | $0.000020 |

## Misses (the outcome differed from the label)
- P09#0 (hard): "['The Midnight Library'] -> A Man Called Ove" expected true, got "unsettled"; answers {"fit": 0.65}
- P09#1 (hard): "['The Midnight Library'] -> A Man Called Ove" expected true, got "unsettled"; answers {"fit": 0.65}
- P12#0: "['Fourth Wing'] -> The Invisible Life of Addie LaRue" expected true, got "unsettled"; answers {"fit": 0.53}
- P12#1: "['Fourth Wing'] -> The Invisible Life of Addie LaRue" expected true, got "unsettled"; answers {"fit": 0.55}
