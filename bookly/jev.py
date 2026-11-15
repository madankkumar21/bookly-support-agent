"""The one door to Jev, TypeSafe's decision model.

Jev answers typed questions about the state a request carries, and each answer is a probability. It keeps
nothing between calls and it writes no text. Almost every question in this repo is a Noul: a yes/no question
whose answer is P(yes). One is a Score: a position on levels that the question describes (the customer's mood). The wording, and the decisions built on the answers, live in bookly/judgments.py. This
module only sends, logs and counts.

Three rules it enforces:
- The exact request payload and the answers go to logs/jev_calls.jsonl, so any result can be rerun.
- A failed call raises JevError. It is never turned into an answer; the caller takes its safe path.
- Spend is summed from that log across every run on this machine, and calls stop at the budget.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from bookly import config


class JevError(Exception):
    """A Jev call failed. Never an answer: callers fall back to what they do without Jev."""


class JevBudgetExceeded(JevError):
    pass


@dataclass
class JevAnswer:
    purpose: str
    probs: dict[str, float]  # question id -> P(yes)
    model: str
    input_tokens: int
    cost_usd: float
    latency_ms: int
    request_id: str | None = None
    # Score questions only: question id -> the probability of each level, in the order the levels were written.
    scores: dict[str, list[float]] = field(default_factory=dict)


_lock = threading.Lock()  # one writer to the log, and one reader of the running total, at a time


def _dump(question) -> dict:
    return question.model_dump(mode="json", exclude_none=True) if hasattr(question, "model_dump") else dict(question)


def spent_usd(log_path: Path | None = None) -> float:
    """Total Jev spend recorded on this machine."""
    path = Path(log_path or config.JEV_LOG)
    if not path.exists():
        return 0.0
    total = 0.0
    for line in path.read_text().splitlines():
        try:
            total += float(json.loads(line).get("cost_usd") or 0.0)
        except (ValueError, AttributeError):
            continue
    return total


class Jev:
    def __init__(self, client=None, model: str | None = None, log_path: Path | None = None, budget_usd: float | None = None):
        self._client = client
        self.model = model or config.JEV_MODEL
        self.log_path = Path(log_path or config.JEV_LOG)
        self.budget_usd = config.JEV_BUDGET_USD if budget_usd is None else budget_usd
        self._spent: float | None = None  # read from the log on first use
        self.spent_here = 0.0  # this instance's own calls only: what one eval run reports as its Jev cost

    def _get_client(self):
        if self._client is None:
            from typesafe_sdk import RetryPolicy, TypeSafeClient, TypeSafeError

            try:
                self._client = TypeSafeClient(retry=RetryPolicy(max_retries=1, timeout=config.JEV_TIMEOUT_S))
            except TypeSafeError as exc:  # no key, or a malformed one
                raise JevError(f"no usable TYPESAFE_API_KEY: {exc}") from exc
        return self._client

    def _write(self, row: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def ask(self, purpose: str, state, questions: dict) -> JevAnswer:
        """Send one request. Returns P(yes) for every question, or raises JevError."""
        if not questions:
            return JevAnswer(purpose, {}, self.model, 0, 0.0, 0)
        row = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"), "purpose": purpose, "model": self.model,
            "request": {"state": state, "questions": {qid: _dump(q) for qid, q in questions.items()}},
        }
        with _lock:
            if self._spent is None:
                self._spent = spent_usd(self.log_path)
            if self._spent >= self.budget_usd:
                raise JevBudgetExceeded(f"Jev budget of ${self.budget_usd:.2f} is used up (${self._spent:.4f} spent)")
        t0 = time.monotonic()
        try:
            resp = self._get_client().system_one(state, questions, model=self.model)
            probs, scores = {}, {}
            for qid in questions:
                a = resp.answers[qid]
                if getattr(a, "noul", None) is not None:
                    probs[qid] = float(a.noul)
                else:  # a Score: keep the whole distribution, so code can read a level and not a blurred mean
                    scores[qid] = [float(p) for _, p in sorted(a.probabilities.items())]
        except JevError:
            raise
        except Exception as exc:  # timeouts, rate limits, a 4xx, a missing answer: all errors, none an answer
            row.update(error=f"{type(exc).__name__}: {str(exc)[:300]}", latency_ms=int((time.monotonic() - t0) * 1000))
            with _lock:
                self._write(row)
            raise JevError(row["error"]) from exc
        latency = int((time.monotonic() - t0) * 1000)
        tokens = int(getattr(resp.usage, "input_tokens", 0) or 0)
        cost = tokens * config.JEV_USD_PER_MTOK_INPUT / 1_000_000
        answer = JevAnswer(purpose, probs, getattr(resp, "model", self.model), tokens, cost, latency,
                           getattr(resp, "request_id", None), scores)
        row.update(model=answer.model, answers=probs, **({"scores": scores} if scores else {}), input_tokens=tokens, cost_usd=round(cost, 8),
                   latency_ms=latency, request_id=answer.request_id, error=None)
        with _lock:
            self._spent = (self._spent or 0.0) + cost
            self.spent_here += cost
            self._write(row)
        return answer
