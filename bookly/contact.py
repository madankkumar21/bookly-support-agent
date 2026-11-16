"""How a verified customer's last conversation ended, kept so the next one can start from it.

A long-running support agent should know that a customer left angry and unresolved, or that a person never
answered a hand-off, and bring a person in sooner. This module holds that record and reads it on return.

Who knows what:
- Code knows what was DONE: a return, a hand-off ticket and whether a person answered it in time, a refund
  offer left unconfirmed, a refusal. None of that needs a model.
- Jev judges what only language shows: how frustrated the customer was (a Score), and whether they said
  they were giving up or that the problem was solved (two Nouls). judgments.mood_questions().
- Code combines both in judgments.decide_return_contact().

What is stored: values only (flags, a ticket id, three labels). Never the customer's words. Same identity
wall as memory: one record per email, written and read only after get_order has verified an order.

What it never does: change a refund decision. An angry customer gets a person sooner, not money.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from bookly import judgments
from bookly.missions import _human, add_business_days

WHAT = {  # how the model is told the last contact ended; every word here is written by code
    "refused": "a refund request that was not eligible",
    "quote_abandoned": "a refund offer that the customer did not confirm",
    "nothing_done": "no action recorded",
    # The ticket and resolved endings never reach the two lines that use WHAT today (judgments.decide_return_contact
    # sends them elsewhere). They are here so a change to that table cannot raise inside get_order.
    "handoff_overdue": "a hand-off to a person that was not answered in time",
    "handoff_pending": "a hand-off to a person that is still open",
    "handoff_answered": "a hand-off that a person answered",
    "handoff_followed_up": "a hand-off that Bookly is following up",
    "resolved": "a request that was resolved",
}


@dataclass
class Contact:
    email: str
    session_id: str
    on: str  # ISO date of the latest turn
    returned: bool = False  # a return was recorded
    other_done: bool = False  # a password reset was sent, or the customer closed a follow-up
    refused: bool = False  # a refund was checked and was not eligible
    quote_pending: bool = False  # a refund offer was shown and never confirmed or declined
    ticket_id: str | None = None  # the hand-off ticket, if a person was brought in
    carried_ticket_id: str | None = None  # an unanswered ticket from an earlier conversation: still open
    mood: str = "unknown"  # calm | concerned | angry | unknown: at the customer's latest judged message
    gave_up: str = "unknown"  # yes | no | unsettled | unknown: yes stays yes for the rest of the conversation
    said_solved: str = "unknown"  # at the latest judged message


def reply_due_on(ticket, policy) -> date:
    return add_business_days(date.fromisoformat(ticket.opened_on), int(policy.get("support.human_reply_business_days")))


def live_ticket(contact: Contact, backend, missions=None):
    """The ticket a person should be working on: the hand-off, or a later ticket that took it over (a priority
    ticket from this module, or the ticket a follow-up opened when it escalated)."""
    by_id = {t.ticket_id: t for t in backend.tickets}
    t = by_id.get(contact.ticket_id)
    for _ in range(len(by_id)):
        if t is None:
            break
        later = t.escalated_to or next((m.ticket_id for m in (missions.items if missions else [])
                                        if m.origin.get("ticket_id") == t.ticket_id and m.ticket_id), None)
        if later not in by_id or later == t.ticket_id:
            break
        t = by_id[later]
    return t


def ended(contact: Contact, backend, policy, missions=None) -> str:
    """One of judgments.ENDED, from what code recorded. Read on return, because 'overdue' depends on today."""
    t = live_ticket(contact, backend, missions)
    if t is not None:
        if t.answered_on:
            return "handoff_answered"
        # One owner per case: a follow-up that is still running for this ticket (bookly/missions.py) already
        # asks the customer and escalates by its own rules, so this module leaves the case to it.
        owners = [m for m in (missions.items if missions else []) if m.origin.get("ticket_id") == t.ticket_id]
        if any(m.status in ("scheduled", "awaiting_reply") for m in owners):
            return "handoff_followed_up"
        if any(m.status == "closed_resolved" for m in owners):  # the customer told the follow-up it arrived
            return "resolved"
        return "handoff_overdue" if backend.today > reply_due_on(t, policy) else "handoff_pending"
    if contact.returned:
        return "resolved"
    if contact.refused:
        return "refused"
    if contact.quote_pending:
        return "quote_abandoned"
    return "resolved" if contact.other_done or contact.said_solved == "yes" else "nothing_done"


class Contacts:
    def __init__(self) -> None:
        self.by_email: dict[str, Contact] = {}

    def prior(self, email: str, session_id: str) -> Contact | None:
        """The record left by an EARLIER conversation, or None."""
        c = self.by_email.get(email)
        return c if c and c.session_id != session_id else None

    def _mine(self, email: str, session, store) -> Contact:
        today, c = store.backend.today, self.by_email.get(email)
        if c is None or c.session_id != session.session_id:
            # A new conversation replaces the earlier record. A ticket that no person has answered is still
            # open, so it is carried over: a visit in between must not make the system forget it.
            t = live_ticket(c, store.backend, store.missions) if c else None
            c = self.by_email[email] = Contact(email=email, session_id=session.session_id, on=today.isoformat(),
                                               carried_ticket_id=t.ticket_id if t and not t.answered_on else None)
        c.on = today.isoformat()
        return c

    def record_facts(self, email: str, session, refusals: int, store, closed_follow_up: bool = False) -> None:
        """After every turn: what code did in this conversation so far."""
        c = self._mine(email, session, store)
        kinds = {a.kind for a in session.actions}
        q = session.pending_confirmation()
        c.returned = "return_created" in kinds
        c.other_done = "password_reset_requested" in kinds or closed_follow_up  # "it arrived" settles the visit
        c.refused, c.quote_pending = refusals > 0, q is not None
        c.ticket_id = session.handoff["ticket_id"] if session.handoff else c.carried_ticket_id

    def record_mood(self, email: str, session, mood: str, gave_up: str, said_solved: str, store) -> None:
        c = self._mine(email, session, store)
        c.mood, c.said_solved = mood, said_solved
        c.gave_up = "yes" if "yes" in (c.gave_up, gave_up) else gave_up

    def snapshot(self, backend, policy, missions=None) -> dict:
        return {email: {**{k: v for k, v in asdict(c).items() if k not in ("email", "session_id", "carried_ticket_id")},
                        "ended": ended(c, backend, policy, missions)} for email, c in self.by_email.items()}


def read_mood(store, session, email: str, answer) -> None:
    """Turn one Jev answer (the mood questions) into the record. Called from memory.remember."""
    mood = judgments.decide_mood(answer.scores.get("frustration"))
    gave_up, solved = judgments.band(answer.probs["gave_up"]), judgments.band(answer.probs["said_solved"])
    store.contacts.record_mood(email, session, mood, gave_up, solved, store)
    levels = answer.scores.get("frustration") or []
    shown = {**{m: round(p, 2) for m, p in zip(judgments.MOODS, levels, strict=False)},
             "gave_up": round(answer.probs["gave_up"], 2), "said_solved": round(answer.probs["said_solved"], 2)}
    session.log("jev", purpose="mood", answers=shown,
                decision=f"mood {mood}; gave up: {gave_up}; said solved: {solved} (kept as how this contact ends)")


def on_return(store, session, toolbox, email: str) -> dict | None:
    """Run once, when an order is first verified. Reads the earlier record, applies the truth table, and for
    an overdue hand-off opens the priority ticket. Returns {outcome, first, later} or None."""
    prior = store.contacts.prior(email, session.session_id)
    if prior is None:
        return None
    b, kb = store.backend, store.kb
    how = ended(prior, b, store.policy, store.missions)
    outcome = judgments.decide_return_contact(how, prior.mood, prior.gave_up)
    session.log("return_contact", ended=how, mood=prior.mood, gave_up=prior.gave_up, decision=outcome)
    day = _human(date.fromisoformat(prior.on))
    quiet = "Do not say anything about how the customer sounded."
    if outcome == "priority_handoff":
        old = live_ticket(prior, b, store.missions)
        result = toolbox.handoff(
            "handoff_overdue",
            f"Ticket {old.ticket_id} was opened on {old.opened_on} and no person replied within the promised time. "
            "The customer has come back. Treat this as a priority.",
            extra={"priority": True, "previous_ticket": {"ticket_id": old.ticket_id, "opened_on": old.opened_on,
                                                         "reason_code": old.reason_code}})
        if result["ticket_id"] != old.ticket_id:
            old.escalated_to = result["ticket_id"]
        message = kb.message("handoff_overdue", old_ticket_id=old.ticket_id, ticket_id=result["ticket_id"])
        return {"outcome": outcome, "later": None,
                "first": f"Last contact ({day}): the hand-off to a person (ticket {old.ticket_id}) was not answered "
                         f"in time. The system has opened priority ticket {result['ticket_id']}. Give the customer "
                         f"this message, word for word, before anything else: {message}"}
    if outcome == "pending_ticket":
        t = live_ticket(prior, b, store.missions)
        line = (f"Last contact ({day}): ticket {t.ticket_id} is open with a person, who will reply by email by "
                f"{_human(reply_due_on(t, store.policy))}. Tell the customer this. Do not open another ticket for "
                "the same issue.")
        return {"outcome": outcome, "first": line, "later": line}
    if outcome == "early_escalation":
        toolbox.escalate_early = True
        return {"outcome": outcome,
                "first": f"Last contact ({day}) ended without a resolution: {WHAT[how]}. In your next reply, say in "
                         "one sentence that you can see the last contact did not resolve it, and offer to connect "
                         "the customer with a person. If they accept, call handoff_to_human with reason_code "
                         f"customer_request. {quiet}",
                "later": f"Last contact ({day}) ended without a resolution, and a person has been offered. If the "
                         f"customer accepts, call handoff_to_human with reason_code customer_request. {quiet}"}
    if outcome == "acknowledge":
        return {"outcome": outcome, "later": None,
                "first": f"Last contact ({day}) ended without a resolution: {WHAT[how]}. In your next reply, say in "
                         f"one sentence that you can see that, then help as usual. {quiet}"}
    return {"outcome": outcome, "first": None, "later": None}
