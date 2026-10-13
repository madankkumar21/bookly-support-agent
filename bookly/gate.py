"""The action gate. Every write passes through here, and none of it reads the model's words.

- Confirmation is taken from the customer's own reply to a code-rendered card (button or a
  whole-message "yes"), never from the model.
- A refund needs: a verified order, the latest open quote, an eligible decision under the
  approval cap, and the customer's confirmation of that exact quote.
- quote_id is the idempotency key: the same quote can never refund twice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bookly.backend import Backend, ReturnRecord
from bookly.policy import Policy
from bookly.state import Session

# Whole-message allowlists. Anything else is "unclear" and the customer is asked again.
# "ok", "sure" and "sounds good" are left out on purpose: they are often acknowledgements, not a yes to money.
YES = {
    "yes", "y", "yeah", "yep", "yup", "confirm", "confirmed", "i confirm",
    "go ahead", "please do", "do it", "yes please", "please go ahead", "yes go ahead",
    "yes thats right", "yes that's right", "yes confirm", "confirm please", "please confirm",
}
NO = {
    "no", "n", "nope", "cancel", "no thanks", "no thank you", "dont", "don't", "stop", "not now",
    "no dont", "no don't", "please cancel", "cancel it", "never mind", "nevermind",
}


def normalize(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"[^\w\s']", " ", t)
    return " ".join(t.split())


def classify_confirmation(text: str) -> str:
    """Return 'confirm', 'decline' or 'unclear'. Only an exact whole-message match confirms."""
    t = normalize(text)
    if t in YES:
        return "confirm"
    if t in NO or t.startswith("no ") or t.startswith("cancel "):
        return "decline"
    return "unclear"


def register_customer_reply(session: Session, text: str, button: str | None = None, quote_id: str | None = None) -> str | None:
    """Called by the orchestrator, in code, before the model sees the customer's message.

    Only applies when a confirmation card is waiting. Returns the signal, or None if no card is waiting.
    A button press names the quote on its card; a press on an older card never confirms newer terms.
    """
    session.last_confirmation_signal = None
    quote = session.pending_confirmation()
    if quote is None:
        return None
    if button in ("confirm", "cancel") and quote_id is not None and quote_id != quote.quote_id:
        session.last_confirmation_signal = "stale_card"
        session.log("confirmation", quote_id=quote.quote_id, signal="stale_card", source="button", text=f"pressed on {quote_id}")
        return "stale_card"
    if button in ("confirm", "cancel"):
        signal = "confirm" if button == "confirm" else "decline"
        source = "button"
    else:
        signal = classify_confirmation(text)
        source = "typed"
    if signal == "confirm":
        quote.confirmation = "confirmed"
    elif signal == "decline":
        quote.confirmation = "declined"
        quote.status = "void"
    session.last_confirmation_signal = signal
    session.log("confirmation", quote_id=quote.quote_id, signal=signal, source=source, text=text)
    return signal


@dataclass
class GateResult:
    allowed: bool
    status: str  # allowed | already_exists | blocked
    reason: str
    existing: ReturnRecord | None = None


def check_create_return(session: Session, backend: Backend, policy: Policy, quote_id: str) -> GateResult:
    existing = backend.find_return_by_quote(quote_id)
    if existing:
        return GateResult(False, "already_exists", "This quote was already used. Same return, same refund.", existing)

    quote = session.quotes.get(quote_id)
    if quote is None:
        return GateResult(False, "blocked", "unknown_quote")
    if quote.quote_id != session.latest_quote_id or quote.status == "void":
        reason = "customer_declined" if quote.confirmation == "declined" else "stale_quote"
        return GateResult(False, "blocked", reason)
    if quote.status != "open":
        return GateResult(False, "blocked", f"quote_{quote.status}")
    if quote.order_id not in session.verified_orders:
        return GateResult(False, "blocked", "not_verified")
    if quote.decision.decision == "needs_human":
        return GateResult(False, "blocked", "needs_human_approval")
    if not quote.decision.refundable:
        return GateResult(False, "blocked", "not_eligible")
    if quote.decision.amount > policy.approval_cap:  # defence in depth: the engine already checks this
        return GateResult(False, "blocked", "needs_human_approval")
    if not quote.presented:
        return GateResult(False, "blocked", "terms_not_shown_to_customer")
    if quote.confirmation != "confirmed":
        return GateResult(False, "blocked", "awaiting_customer_confirmation")
    returned = backend.returned_item_ids(quote.order_id)
    if any(line.item_id in returned for line in quote.decision.lines):
        return GateResult(False, "blocked", "already_returned")
    return GateResult(True, "allowed", "verified, latest quote, eligible, under cap, confirmed by customer")
