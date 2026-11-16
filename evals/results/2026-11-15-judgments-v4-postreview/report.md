# Judgments eval: v4-postreview

Model `jev-1.14.0`, k=2, evals/judgment_set.yaml (synthetic), bands yes ≥ 0.7, no ≤ 0.3, close ≥ 0.85, run 2026-11-15T10:40:34.

## Headline
- **Outcome accuracy 94%** over 164 judged items (each scored through its truth table). Errors: 0.
- **Wrong-direction outcomes: 0** (a taste saved from a special-treatment message, a follow-up closed without the customer saying it arrived, a clear non-fit rated yes, or a person brought in early for a calm customer).
- Mood label accuracy (calm / concerned / angry, before the table): 81%.
- Held-out items (added after a wording change, never used to word a question): 8 of 8 correct.
- Spend $0.009807.

## By judgment
| Judgment | Runs | Accuracy | Accuracy, clear items | Wrong direction | Unsettled | Same outcome every run | p50 | Tokens/call | Cost/call |
|---|---|---|---|---|---|---|---|---|---|
| remember | 48 | 100% | 100% | 0 | 0% | 24/24 | 86 ms | 2098 | $0.000088 |
| follow_up | 44 | 100% | 100% | 0 | 14% | 22/22 | 67 ms | 469 | $0.000020 |
| fit | 24 | 83% | 91% | 0 | 17% | 12/12 | 67 ms | 476 | $0.000020 |
| mood | 48 | 90% | 94% | 0 | 4% | 23/24 | 85 ms | 2098 | $0.000088 |

## Misses (the outcome differed from the label)
- P09#0 (hard): "['The Midnight Library'] -> A Man Called Ove" expected true, got "unsettled"; answers {"fit": 0.64}
- P09#1 (hard): "['The Midnight Library'] -> A Man Called Ove" expected true, got "unsettled"; answers {"fit": 0.64}
- P12#0: "['Fourth Wing'] -> The Invisible Life of Addie LaRue" expected true, got "unsettled"; answers {"fit": 0.56}
- P12#1: "['Fourth Wing'] -> The Invisible Life of Addie LaRue" expected true, got "unsettled"; answers {"fit": 0.58}
- M01#0: "OK, thanks anyway." expected ["none"], got "acknowledge"; answers {"calm": 0.25, "concerned": 0.75, "angry": 0.0, "gave_up": 0.3, "said_solved": 0.07}; mood concerned
- M01#1: "OK, thanks anyway." expected ["none"], got "acknowledge"; answers {"calm": 0.27, "concerned": 0.73, "angry": 0.0, "gave_up": 0.3, "said_solved": 0.08}; mood concerned
- M19#1 (hard): "Can you check on my order of the book I HATE EVERYTHING ABOUT YOU?" expected ["acknowledge", "early_escalation"], got "none"; answers {"calm": 0.61, "concerned": 0.27, "angry": 0.12, "gave_up": 0.02, "said_solved": 0.01}; mood calm
- M22#0 (hard): "I don't want to give up on this book. Can I exchange it for the paperback?" expected ["none"], got "acknowledge"; answers {"calm": 0.29, "concerned": 0.71, "angry": 0.0, "gave_up": 0.02, "said_solved": 0.02}; mood concerned
- M22#1 (hard): "I don't want to give up on this book. Can I exchange it for the paperback?" expected ["none"], got "acknowledge"; answers {"calm": 0.27, "concerned": 0.73, "angry": 0.0, "gave_up": 0.02, "said_solved": 0.02}; mood concerned
