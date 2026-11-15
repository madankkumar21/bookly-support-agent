"""A scripted stand-in for the TypeSafe client, so no test calls or pays for the real Jev."""

from __future__ import annotations

from types import SimpleNamespace

from bookly.jev import Jev


class ScriptedJevClient:
    """answers: {question id: P(yes)}, or a function (state, questions) -> that dict. Unlisted ids get `default`."""

    def __init__(self, answers=None, default: float = 0.05, tokens: int = 200, fail: Exception | None = None):
        self.answers, self.default, self.tokens, self.fail = answers or {}, default, tokens, fail
        self.calls: list[dict] = []

    def system_one(self, state, questions, model=None, **kwargs):
        self.calls.append({"state": state, "questions": dict(questions), "model": model})
        if self.fail:
            raise self.fail
        probs = self.answers(state, questions) if callable(self.answers) else self.answers
        def one(qid, q):
            if getattr(q, "type", None) == "score":  # a Score: {level number: probability}; default = the first level
                n = len(q.criteria)
                levels = probs.get(qid) or [1.0] + [0.0] * (n - 1)
                return SimpleNamespace(noul=None, probabilities=dict(enumerate(levels, start=1)))
            return SimpleNamespace(noul=probs.get(qid, self.default))

        return SimpleNamespace(
            answers={qid: one(qid, q) for qid, q in questions.items()},
            usage=SimpleNamespace(input_tokens=self.tokens, output_tokens=0), model=model, request_id="req-test",
        )


def scripted_jev(answers=None, tmp_path=None, **kwargs) -> Jev:
    client = ScriptedJevClient(answers, **{k: v for k, v in kwargs.items() if k in ("default", "tokens", "fail")})
    jev = Jev(client=client, log_path=(tmp_path / "jev_calls.jsonl") if tmp_path else None,
              budget_usd=kwargs.get("budget_usd"))
    jev.client_for_tests = client
    return jev
