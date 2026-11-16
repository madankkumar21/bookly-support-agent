# Judgments eval: sonnet-v4-postreview

Model `claude-sonnet-5-5`, k=2, evals/judgment_set.yaml (synthetic), bands yes ≥ 0.7, no ≤ 0.3, close ≥ 0.85, run 2026-11-15T10:42:34.

## Headline
- **Outcome accuracy 98%** over 164 judged items (each scored through its truth table). Errors: 0.
- **Wrong-direction outcomes: 0** (a taste saved from a special-treatment message, a follow-up closed without the customer saying it arrived, a clear non-fit rated yes, or a person brought in early for a calm customer).
- Mood label accuracy (calm / concerned / angry, before the table): 90%.
- Held-out items (added after a wording change, never used to word a question): 8 of 8 correct.
- Spend $1.478354.

## By judgment
| Judgment | Runs | Accuracy | Accuracy, clear items | Wrong direction | Unsettled | Same outcome every run | p50 | Tokens/call | Cost/call |
|---|---|---|---|---|---|---|---|---|---|
| remember | 48 | 100% | 100% | 0 | 0% | 24/24 | 2861 ms | 5151 | $0.014228 |
| follow_up | 44 | 100% | 100% | 0 | 9% | 22/22 | 1399 ms | 760 | $0.001731 |
| fit | 24 | 100% | 100% | 0 | 0% | 12/12 | 1301 ms | 711 | $0.001529 |
| mood | 48 | 92% | 94% | 0 | 15% | 24/24 | 2869 ms | 5151 | $0.014220 |

## Misses (the outcome differed from the label)
- M01#0: "OK, thanks anyway." expected ["none"], got "acknowledge"; answers {"calm": 1.0, "concerned": 0.0, "angry": 0.0, "gave_up": 0.5, "said_solved": 0.0}; mood calm
- M01#1: "OK, thanks anyway." expected ["none"], got "acknowledge"; answers {"calm": 1.0, "concerned": 0.0, "angry": 0.0, "gave_up": 0.5, "said_solved": 0.0}; mood calm
- M19#0 (hard): "Can you check on my order of the book I HATE EVERYTHING ABOUT YOU?" expected ["acknowledge", "early_escalation"], got "none"; answers {"calm": 1.0, "concerned": 0.0, "angry": 0.0, "gave_up": 0.0, "said_solved": 0.0}; mood calm
- M19#1 (hard): "Can you check on my order of the book I HATE EVERYTHING ABOUT YOU?" expected ["acknowledge", "early_escalation"], got "none"; answers {"calm": 1.0, "concerned": 0.0, "angry": 0.0, "gave_up": 0.0, "said_solved": 0.0}; mood calm
