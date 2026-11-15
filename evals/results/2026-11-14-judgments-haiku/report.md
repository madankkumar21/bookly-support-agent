# Judgments eval: haiku

Model `claude-haiku-5-5`, k=2, evals/judgment_set.yaml (synthetic), bands yes ≥ 0.7, no ≤ 0.3, close ≥ 0.85, run 2026-11-14T15:03:13.

## Headline
- **Outcome accuracy 95%** over 116 judged items (each scored through its truth table). Errors: 0.
- **Wrong-direction outcomes: 0** (a taste saved from a special-treatment message, a follow-up closed without the customer saying it arrived, or a clear non-fit rated yes).
- Held-out items (added after a wording change, never used to word a question): 4 of 8 correct.
- Spend $0.036750.

## By judgment
| Judgment | Runs | Accuracy | Accuracy, clear items | Wrong direction | Unsettled | Same outcome every run | p50 | Tokens/call | Cost/call |
|---|---|---|---|---|---|---|---|---|---|
| remember | 48 | 92% | 91% | 0 | 8% | 22/24 | 2178 ms | 4623 | $0.000652 |
| follow_up | 44 | 96% | 100% | 0 | 0% | 22/22 | 1196 ms | 731 | $0.000084 |
| fit | 24 | 100% | 100% | 0 | 0% | 12/12 | 1803 ms | 682 | $0.000074 |

## Misses (the outcome differed from the label)
- F14#0 (hard): ["Please mark this as resolved."] expected ["close", "ask"], got "no_change"; answers {"arrived": 0.0, "not_arrived": 0.0}
- F14#1 (hard): ["Please mark this as resolved."] expected ["close", "ask"], got "no_change"; answers {"arrived": 0.0, "not_arrived": 0.0}
- R21#1: "I read a lot of biographies." expected {"likes": ["memoir_biography"]}, got {"likes": [], "dislikes": []}; answers {"lasting": 1.0, "special_treatment": 0.0, "likes:literary_fiction": 0.5, "dislikes:literary_fiction": 0.5, "likes:science_fiction": 0.5, "dislikes:science_fiction": 0.5, "likes:fantasy": 0.5, "dislikes:fantasy": 0.5, "likes:romance": 0.5, "dislikes:romance": 0.5, "likes:historical_fiction": 0.5, "dislikes:historical_fiction": 0.5, "likes:mystery_thriller:mysteries": 0.5, "dislikes:mystery_thriller:mysteries": 0.5, "likes:mystery_thriller:thrillers": 0.5, "dislikes:mystery_thriller:thrillers": 0.5, "likes:horror": 0.5, "dislikes:horror": 0.5, "likes:memoir_biography:memoirs": 0.5, "dislikes:memoir_biography:memoirs": 0.5, "likes:memoir_biography:biographies": 1.0, "likes:popular_science": 0.5, "dislikes:popular_science": 0.5, "likes:self_help": 0.5, "dislikes:self_help": 0.5}; a taste was stated, but no genre on the list was settled
- R22#0: "I love a good thriller." expected {"likes": ["mystery_thriller"]}, got {"likes": [], "dislikes": []}; answers {"lasting": 0.5, "special_treatment": 0.0, "likes:mystery_thriller:thrillers": 1.0}; no lasting taste stated (unsettled)
- R22#1: "I love a good thriller." expected {"likes": ["mystery_thriller"]}, got {"likes": [], "dislikes": []}; answers {"lasting": 0.5, "special_treatment": 0.0, "dislikes:literary_fiction": 0.5, "dislikes:science_fiction": 0.5, "dislikes:fantasy": 0.5, "dislikes:romance": 0.5, "dislikes:historical_fiction": 0.5, "dislikes:mystery_thriller:mysteries": 0.5, "likes:mystery_thriller:thrillers": 1.0, "dislikes:horror": 0.5, "dislikes:memoir_biography:memoirs": 0.5, "dislikes:memoir_biography:biographies": 0.5, "dislikes:popular_science": 0.5, "dislikes:self_help": 0.5}; no lasting taste stated (unsettled)
- R24#1: "Biographies bore me." expected {"dislikes": ["memoir_biography"]}, got {"likes": [], "dislikes": []}; answers {"lasting": 1.0, "special_treatment": 0.0, "likes:literary_fiction": 0.5, "dislikes:literary_fiction": 0.5, "likes:science_fiction": 0.5, "dislikes:science_fiction": 0.5, "likes:fantasy": 0.5, "dislikes:fantasy": 0.5, "likes:romance": 0.5, "dislikes:romance": 0.5, "likes:historical_fiction": 0.5, "dislikes:historical_fiction": 0.5, "likes:mystery_thriller:mysteries": 0.5, "dislikes:mystery_thriller:mysteries": 0.5, "likes:mystery_thriller:thrillers": 0.5, "dislikes:mystery_thriller:thrillers": 0.5, "likes:horror": 0.5, "dislikes:horror": 0.5, "likes:memoir_biography:memoirs": 0.5, "dislikes:memoir_biography:memoirs": 0.5, "dislikes:memoir_biography:biographies": 1.0, "likes:popular_science": 0.5, "dislikes:popular_science": 0.5, "likes:self_help": 0.5, "dislikes:self_help": 0.5}; a taste was stated, but no genre on the list was settled
