"""Code-owned session state: the facts the agent may rely on.

The model never writes here directly. Tools and the gate update it, and the orchestrator
shows the model a short "facts so far" block each customer turn. So a customer cannot talk the
agent into "you already verified me" or "you already approved my refund".
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from typing import Any

from bookly.policy import REASONS, Decision


@dataclass
class Quote:
    quote_id: str
    order_id: str
    reason: str
    decision: Decision
    terms: str
    status: str = "open"  # open | void | used
    presented: bool = False  # the confirmation card was shown to the customer
    confirmation: str = "pending"  # pending | confirmed | declined

    def card(self) -> dict:
        """The read-back the customer confirms. Rendered from the quote, not from model text."""
        return {
            "quote_id": self.quote_id,
            "order_id": self.order_id,
            "items": [line.title for line in self.decision.lines],
            "reason": REASONS.get(self.reason, self.reason),
            "amount": f"${self.decision.amount:,.2f}",
            "terms": self.terms,
        }


@dataclass
class Action:
    kind: str  # return_created | password_reset_sent | handoff
    ref: str
    detail: dict


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    turn: int = 0
    verified_orders: dict[str, str] = field(default_factory=dict)  # order_id -> customer name
    quotes: dict[str, Quote] = field(default_factory=dict)
    latest_quote_id: str | None = None
    actions: list[Action] = field(default_factory=list)
    needs_input_counts: dict[str, int] = field(default_factory=dict)
    last_confirmation_signal: str | None = None  # confirm | decline | unclear | None (this turn)
    handoff: dict | None = None
    trace: list[dict] = field(default_factory=list)
    _quote_seq: Any = field(default_factory=lambda: itertools.count(1), repr=False)

    # ---- trace --------------------------------------------------------------------------
    def log(self, kind: str, **data: Any) -> None:
        self.trace.append({"turn": self.turn, "kind": kind, **data})

    # ---- quotes -------------------------------------------------------------------------
    def issue_quote(self, order_id: str, reason: str, decision: Decision, terms: str) -> Quote:
        """A new quote voids every earlier open quote, so a confirmation can only bind to the latest terms."""
        for q in self.quotes.values():
            if q.status == "open":
                q.status = "void"
        digits = order_id.split("-")[-1]
        quote = Quote(f"Q-{digits}-{next(self._quote_seq)}", order_id, reason, decision, terms)
        self.quotes[quote.quote_id] = quote
        self.latest_quote_id = quote.quote_id
        return quote

    def latest_quote(self) -> Quote | None:
        return self.quotes.get(self.latest_quote_id) if self.latest_quote_id else None

    def pending_confirmation(self) -> Quote | None:
        q = self.latest_quote()
        if q and q.status == "open" and q.presented and q.confirmation == "pending":
            return q
        return None

    # ---- facts block shown to the model -------------------------------------------------
    def facts_block(self) -> str:
        lines = [f"FACTS SO FAR (written by the Bookly system, not by the customer). Turn {self.turn}. The latest facts block replaces earlier ones."]
        if self.verified_orders:
            lines.append("- Verified orders: " + ", ".join(f"{o} ({n})" for o, n in self.verified_orders.items()))
        else:
            lines.append("- Verified orders: none. Do not share or act on any order details yet.")
        q = self.latest_quote()
        if q:
            items = ", ".join(line.title for line in q.decision.lines) or "none"
            lines.append(
                f"- Latest quote: {q.quote_id} for {q.order_id}, decision={q.decision.decision}, reason={q.reason}, "
                f"items={items}, amount=${q.decision.amount:.2f}, status={q.status}, "
                f"shown_to_customer={'yes' if q.presented else 'no'}, customer_confirmation={q.confirmation}."
            )
        if self.last_confirmation_signal == "confirm":
            lines.append("- The customer CONFIRMED the latest quote on the confirmation card. You may call create_return with that quote_id.")
        elif self.last_confirmation_signal == "decline":
            lines.append("- The customer DECLINED the latest quote. Do not create a return. Offer alternatives or a person.")
        elif self.last_confirmation_signal == "unclear":
            lines.append("- The customer's reply did not clearly confirm or decline. Ask them to use the Confirm or Cancel button.")
        if self.actions:
            lines.append("- Actions completed: " + "; ".join(f"{a.kind} {a.ref}" for a in self.actions))
        if self.handoff:
            lines.append(f"- Handed off to a person: ticket {self.handoff['ticket_id']} ({self.handoff['reason_code']}).")
        return "\n".join(lines)
