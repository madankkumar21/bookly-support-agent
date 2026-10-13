"""Pinned policy text. Rendered from policy_text.yaml with values from policy.yaml.

The agent may only state policy that a passage here supports. If search finds nothing,
the agent says it does not have that information and offers a person.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from bookly.config import POLICY_TEXT_PATH
from bookly.policy import Decision, Policy

PLACEHOLDER = re.compile(r"\{([a-z_]+(?:\.[a-z_]+)+)\}")
STOPWORDS = {"a", "an", "the", "do", "does", "you", "your", "i", "my", "is", "it", "to", "of", "for", "and", "or", "on", "in", "can", "how", "what"}


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "ly", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    if len(word) > 3 and word[-1] == word[-2]:  # shipp -> ship
        word = word[:-1]
    return word


def _stems(text: str) -> list[str]:
    words = re.findall(r"[a-z']+", (text or "").lower())
    return [_stem(w) for w in words if w not in STOPWORDS]


def _fmt(key: str, value: object) -> str:
    if key.endswith("_usd"):
        return f"${float(value):,.2f}"
    return str(value)


def render(template: str, policy: Policy, **extra: str) -> str:
    def sub(m: re.Match) -> str:
        return _fmt(m.group(1), policy.get(m.group(1)))

    text = PLACEHOLDER.sub(sub, template)
    for k, v in extra.items():
        text = text.replace("{" + k + "}", v)
    return " ".join(text.split())


@dataclass(frozen=True)
class Passage:
    id: str
    title: str
    keywords: tuple[str, ...]
    text: str


class PolicyText:
    def __init__(self, policy: Policy, path: Path = POLICY_TEXT_PATH):
        raw = yaml.safe_load(Path(path).read_text())
        self.policy = policy
        self.raw = raw
        self.passages = [
            Passage(p["id"], p["title"], tuple(k.lower() for k in p["keywords"]), render(p["text"], policy))
            for p in raw["passages"]
        ]
        self._keyword_stems = {
            p.id: {tuple(_stems(k)) for k in (*p.keywords, p.title) if _stems(k)} for p in self.passages
        }
        self._df: dict[tuple, int] = {}
        for kws in self._keyword_stems.values():
            for kw in kws:
                self._df[kw] = self._df.get(kw, 0) + 1
        self.terms_templates: dict[str, str] = raw["terms"]
        self.message_templates: dict[str, str] = raw["messages"]

    def search(self, topic: str, limit: int = 3) -> list[Passage]:
        """Keyword search with light stemming. A keyword that few passages share counts for more,
        so "shipping to Canada" ranks the regions passage above the generic shipping ones."""
        query = set(_stems(topic))
        scored = []
        for p in self.passages:
            score = 0.0
            for kw in self._keyword_stems[p.id]:
                if set(kw) <= query:
                    score += 1.0 / self._df[kw]
            if score > 0:
                scored.append((score, p))
        scored.sort(key=lambda sp: -sp[0])
        return [p for _, p in scored[:limit]]

    def message(self, name: str, **extra: str) -> str:
        """Fixed customer-facing messages the code sends (handoff, password reset, corrections)."""
        return render(self.message_templates[name], self.policy, **extra)

    def terms(self, decision: Decision) -> str:
        """The read-back the customer confirms. Built by code from the decision, never by the model."""
        template = self.terms_templates[decision.decision]
        return render(template, self.policy, amount=f"${decision.amount:,.2f}")
