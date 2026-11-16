"""Follow-ups: a case that Bookly comes back to days after the conversation ended.

This is the long-horizon piece. A follow-up is a small record with a state machine, owned by code:

    scheduled -> awaiting_reply -> closed_resolved | closed_no_reply | escalated

- Code opens one when a refund is created, or when a lost package is handed to a person.
- Code works out the dates. Jev is weak on dates, and code is exact.
- When the clock reaches the due date, code writes a templated email to a simulated outbox.
- When the customer answers in a later conversation, Jev reads the answer (two yes/no questions) and code
  applies the truth table in judgments.decide_follow_up. A button press is read by code alone.
- Code creates the escalation ticket. The conversational model only relays what happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from bookly import config, judgments
from bookly.jev import JevError

OPEN = ("scheduled", "awaiting_reply")
BUTTONS = f"[[options: {judgments.FOLLOW_UP_YES} | {judgments.FOLLOW_UP_NO}]]"


def add_business_days(start: date, n: int) -> date:
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _human(d: date) -> str:
    return f"{d:%A}, {d:%B} {d.day}"


@dataclass
class Mission:
    mission_id: str
    kind: str  # refund_check | lost_package_check
    order_id: str
    email: str
    first_name: str
    subject: str  # built by code, e.g. "the refund of $18.99 for order BK-1001"
    origin: dict  # the refund or the ticket this follows up on
    opened_on: date
    due_on: date
    status: str = "scheduled"
    sent_on: date | None = None
    expires_on: date | None = None
    asks: int = 0  # times the customer's answer was unsettled and Bookly asked again
    outbox_id: str | None = None
    ticket_id: str | None = None
    message_for_customer: str | None = None  # set when a person takes over
    history: list[dict] = field(default_factory=list)

    def note(self, today: date, event: str, **detail) -> None:
        self.history.append({"on": today.isoformat(), "event": event, **detail})

    def view(self) -> dict:
        return {
            "mission_id": self.mission_id, "kind": self.kind, "order_id": self.order_id, "subject": self.subject,
            "origin": self.origin, "status": self.status, "opened_on": self.opened_on.isoformat(),
            "due_on": self.due_on.isoformat(), "sent_on": self.sent_on.isoformat() if self.sent_on else None,
            "asks": self.asks, "ticket_id": self.ticket_id, "history": list(self.history),
        }

    def next_step(self, outcome: str | None = None) -> str:
        """What the conversational model should do about this follow-up, in words the system writes."""
        if self.status == "closed_resolved":
            return (f"Follow-up {self.mission_id}: the customer said {self.subject} arrived, and the system closed it. "
                    "If you have not yet, thank them in one sentence. Do not ask about it again.")
        if self.status == "escalated" and not self.message_for_customer:
            # The clock escalated it (nobody answered the follow-up email), so there is no message to relay.
            return (f"Follow-up {self.mission_id}: the customer did not answer Bookly's email about {self.subject}, so "
                    f"the system passed it to a person (ticket {self.ticket_id}). If you have not yet, tell the "
                    "customer in one sentence that a person has the case and will reply by email. Do not ask about "
                    "it again.")
        if self.status == "closed_no_reply":
            return (f"Follow-up {self.mission_id}: the customer did not answer Bookly's email about {self.subject}, and "
                    "the system stopped waiting for one. Do not ask about it, and do not thank the customer for an answer. "
                    "If the customer raises it, help as usual.")
        if self.status == "escalated":
            return (f"Follow-up {self.mission_id}: the customer said {self.subject} has not arrived, so the system "
                    f"passed it to a person (ticket {self.ticket_id}). If you have not yet, tell the customer "
                    f"exactly this: "
                    f"{self.message_for_customer}")
        if self.status == "awaiting_reply" and outcome == "ask":
            return (f"Follow-up {self.mission_id}: Bookly asked whether {self.subject} arrived, and the customer's "
                    "answer was not clear. Ask once, in one sentence, whether it arrived, and end your message with "
                    f"{BUTTONS}")
        if self.status == "awaiting_reply":
            return (f"Follow-up {self.mission_id}: on {_human(self.sent_on)} Bookly emailed the customer to ask "
                    f"whether {self.subject} arrived. They have not answered yet. Help with what they came for "
                    f"first. Then ask in one sentence whether it arrived, and end your message with {BUTTONS}")
        return f"Follow-up {self.mission_id}: scheduled. Bookly will email the customer on {_human(self.due_on)}."


class Missions:
    def __init__(self) -> None:
        self.items: list[Mission] = []

    def _add(self, **kw) -> Mission:
        m = Mission(mission_id=f"M-{len(self.items) + 1:04d}", **kw)
        m.note(m.opened_on, "opened", due_on=m.due_on.isoformat())
        self.items.append(m)
        return m

    def open_for(self, order_id: str) -> list[Mission]:
        return [m for m in self.items if m.order_id == order_id and m.status in OPEN]

    def awaiting(self, order_ids) -> list[Mission]:
        return [m for m in self.items if m.order_id in order_ids and m.status == "awaiting_reply"]

    def open_refund_check(self, order, rec, today: date, policy) -> Mission:
        due = add_business_days(today, int(policy.get("returns.refund_business_days"))) + timedelta(days=config.FOLLOW_UP_GRACE_DAYS)
        return self._add(
            kind="refund_check", order_id=order.order_id, email=order.email, first_name=order.customer_name.split()[0],
            subject=f"the refund of ${rec.amount:,.2f} for order {order.order_id}",
            origin={"rma_id": rec.rma_id, "refund_id": rec.refund_id, "amount": rec.amount}, opened_on=today, due_on=due,
        )

    def open_lost_package_check(self, order, ticket_id: str, today: date) -> Mission:
        return self._add(
            kind="lost_package_check", order_id=order.order_id, email=order.email,
            first_name=order.customer_name.split()[0], subject=f"the package for order {order.order_id}",
            origin={"ticket_id": ticket_id}, opened_on=today,
            due_on=today + timedelta(days=config.LOST_PACKAGE_CHECK_DAYS),
        )

    def run_due(self, today: date, backend, kb, outbox: list[dict]) -> list[dict]:
        """The scheduled check. Sends what is due and closes or escalates what expired. All dates are code."""
        events = []
        for m in self.items:
            if m.status == "scheduled" and m.due_on <= today:
                template = "follow_up_refund_check" if m.kind == "refund_check" else "follow_up_lost_package_check"
                text = kb.message(template, first_name=m.first_name, order_id=m.order_id,
                                  amount=f"${m.origin.get('amount', 0):,.2f}")
                m.outbox_id = f"OUT-{len(outbox) + 1:04d}"
                outbox.append({"outbox_id": m.outbox_id, "to": m.email, "sent_on": today.isoformat(),
                               "mission_id": m.mission_id, "text": text})
                m.status, m.sent_on = "awaiting_reply", today
                m.expires_on = today + timedelta(days=config.FOLLOW_UP_EXPIRES_DAYS)
                m.note(today, "asked", outbox_id=m.outbox_id)
                events.append({"mission_id": m.mission_id, "event": "asked", "to_status": m.status})
            elif m.status == "awaiting_reply" and m.expires_on and m.expires_on <= today:
                if m.kind == "refund_check":  # no answer about money that was sent: close quietly
                    m.status = "closed_no_reply"
                else:  # no answer about a package that never came: a person should look
                    ticket = backend.create_ticket("followup_unresolved", {
                        "reason_code": "followup_unresolved", "follow_ups": [m.view()],
                        "summary": f"No answer to follow-up {m.mission_id} about {m.subject}."})
                    m.status, m.ticket_id = "escalated", ticket.ticket_id
                m.note(today, "expired", to_status=m.status)
                events.append({"mission_id": m.mission_id, "event": "expired", "to_status": m.status})
        return events


def read_reply(store, session, toolbox, mission: Mission, messages: list[str]) -> str:
    """Read the customer's answer to a follow-up and apply the outcome. Returns close|escalate|ask|no_change.

    Never raises. If Jev is unavailable, nothing changes: an error is not an answer.
    """
    today = store.backend.today
    outcome = judgments.decide_follow_up_button(messages[-1]) if len(messages) == 1 else None
    answers, source, latency = None, "button", 0
    if outcome is None:
        source = "jev"
        try:
            answer = store.jev.ask("follow_up", judgments.follow_up_state(mission.subject, messages),
                                   judgments.follow_up_questions(mission.subject))
        except JevError as exc:
            session.log("jev", purpose="follow_up", mission_id=mission.mission_id, jev_error=str(exc)[:200],
                        decision="no change: Jev was unavailable", to_status=mission.status)
            return "no_change"
        answers = {k: round(v, 2) for k, v in answer.probs.items()}
        latency = answer.latency_ms
        outcome = judgments.decide_follow_up(answer.probs, mission.asks)

    if outcome == "close":
        mission.status = "closed_resolved"
    elif outcome == "escalate":
        result = toolbox.handoff(
            "followup_unresolved",
            f"Follow-up {mission.mission_id}: Bookly asked whether {mission.subject} arrived. The customer says it "
            "has not, or could not say clearly after being asked twice.",
        )  # the ticket carries this follow-up: Toolbox.handoff attaches every one that is waiting
        mission.status, mission.ticket_id = "escalated", result["ticket_id"]
        mission.message_for_customer = result["message_for_customer"]
    elif outcome == "ask":
        mission.asks += 1
    mission.note(today, f"reply_read:{outcome}", source=source, answers=answers)
    session.log("jev" if source == "jev" else "follow_up_button", purpose="follow_up", mission_id=mission.mission_id,
                answers=answers, decision=outcome, to_status=mission.status, latency_ms=latency)
    return outcome
