# Jev judgments eval: jev

Model `jev-1.14.0`, k=2, evals/judgment_set.yaml (synthetic), bands yes ≥ 0.7, no ≤ 0.3, close ≥ 0.85, run 2026-11-13T11:31:50.

## Headline
- **Outcome accuracy 94%** over 108 judged items (each scored through its truth table). Errors: 0.
- **Wrong-direction outcomes: 0** (a taste saved from a special-treatment message, a follow-up closed without the customer saying it arrived, or a clear non-fit rated yes).
- Jev spend $0.004163.

## By judgment
| Judgment | Runs | Accuracy | Accuracy, clear items | Wrong direction | Unsettled | Same outcome every run | p50 | Tokens/call | Cost/call |
|---|---|---|---|---|---|---|---|---|---|
| remember | 40 | 95% | 94% | 0 | 0% | 20/20 | 120 ms | 1676 | $0.000070 |
| follow_up | 44 | 100% | 100% | 0 | 14% | 22/22 | 92 ms | 469 | $0.000020 |
| fit | 24 | 83% | 91% | 0 | 17% | 12/12 | 96 ms | 476 | $0.000020 |

## Misses (the outcome differed from the label)
- P09#0 (hard): "['The Midnight Library'] -> A Man Called Ove" expected true, got "unsettled"; answers {"fit": 0.66}
- P09#1 (hard): "['The Midnight Library'] -> A Man Called Ove" expected true, got "unsettled"; answers {"fit": 0.65}
- P12#0: "['Fourth Wing'] -> The Invisible Life of Addie LaRue" expected true, got "unsettled"; answers {"fit": 0.57}
- P12#1: "['Fourth Wing'] -> The Invisible Life of Addie LaRue" expected true, got "unsettled"; answers {"fit": 0.56}
- R05#0: "Memoirs are my favourite, I read about one a month." expected {"likes": ["memoir_biography"]}, got {"likes": [], "dislikes": []}; answers {"lasting": 0.97, "special_treatment": 0.02}; a taste was stated, but no genre on the list was settled
- R05#1: "Memoirs are my favourite, I read about one a month." expected {"likes": ["memoir_biography"]}, got {"likes": [], "dislikes": []}; answers {"lasting": 0.97, "special_treatment": 0.02}; a taste was stated, but no genre on the list was settled
