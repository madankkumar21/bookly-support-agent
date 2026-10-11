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
        self.terms_templates: dict[str, str] = raw["terms"]

    def search(self, topic: str, limit: int = 2) -> list[Passage]:
        q = f" {(topic or '').lower()} "
        scored = []
        for p in self.passages:
            score = sum(2 if " " in k else 1 for k in p.keywords if k in q)
            score += sum(1 for w in p.title.lower().split() if len(w) > 3 and f" {w} " in q)
            if score > 0:
                scored.append((score, p))
        scored.sort(key=lambda sp: -sp[0])
        return [p for _, p in scored[:limit]]

    def terms(self, decision: Decision) -> str:
        """The read-back the customer confirms. Built by code from the decision, never by the model."""
        template = self.terms_templates[decision.decision]
        return render(template, self.policy, amount=f"${decision.amount:,.2f}")
