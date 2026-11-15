"""The intent router on Jev, as an alternative engine to the Haiku router (BOOKLY_ROUTER_ENGINE=jev).

Same job and same interface as bookly/router.py: label the customer's message, so the agent loads only the
procedures it needs. The difference is the shape of the question. The Haiku router writes a JSON list of
labels and states its own confidence. Jev answers four yes/no questions, one per intent, each with a
probability, and code builds the label list (judgments.decide_route).

Anything uncertain widens what loads, as before: a procedure answer inside the unsettled band, an API error
or an exhausted budget all load every procedure.
"""

from __future__ import annotations

from types import SimpleNamespace

from bookly import config, judgments
from bookly.jev import Jev, JevError
from bookly.router import Route, shadow_tools


class JevRouter:
    def __init__(self, jev: Jev | None = None, threshold: float = judgments.YES):
        self.jev = jev or Jev()
        self.model = self.jev.model
        self.threshold = threshold  # Route.to_load falls back when a procedure answer lies in (1-t, t)

    def classify(self, text: str, last_reply: str = "") -> Route:
        """Never raises: any failure comes back as a Route with error set, which loads every procedure."""
        try:
            answer = self.jev.ask("router", judgments.router_state(text, last_reply), judgments.ROUTER_QUESTIONS)
        except JevError as exc:
            return Route([], 0.0, error=f"{type(exc).__name__}: {str(exc)[:200]}", model=self.model)
        intents, confidence = judgments.decide_route(answer.probs)
        usage = SimpleNamespace(input_tokens=answer.input_tokens, output_tokens=0)  # Jev bills input only
        # probs holds Jev's raw answers (policy is two questions); judgments.intent_probs joins them per intent.
        return Route(intents, confidence, model=answer.model, usage=usage, latency_ms=answer.latency_ms,
                     tools=shadow_tools(intents), probs={k: round(v, 4) for k, v in answer.probs.items()})


def make_router():
    """The router the agent uses when BOOKLY_ROUTER=1."""
    from bookly.router import Router

    return JevRouter() if config.ROUTER_ENGINE == "jev" else Router()
