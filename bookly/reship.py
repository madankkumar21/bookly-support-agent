"""The reship journey (BOOKLY_RESHIP=1, needs BOOKLY_STORE=1). See docs/CU_JOURNEY.md.

One late package, three visits. Who decides what:
- Delay facts decide entitlement. Code reads the order: late, then lost by the existing _likely_lost rule
  (no tracking scan for N business days past the estimate). Mood never changes entitlement.
- Jev reads two things the customer wrote: whether the package arrived (the follow-up questions) and the
  mood (bookly/contact.py). Code applies the truth tables.
- Code writes the reship_request, after four checks: the order is verified in this conversation, it is
  lost, it is under the value cap, and it has no earlier reship or request. The chat agent has no reship
  tool. The order console (/admin) acts only on a pending request that code wrote.
- Mood changes handling only: if the customer's last visit ended angry, code sets the priority flag on the
  request, so a person follows up by email. When the console completes a priority reship, code opens a
  reship_followup ticket for staff (Backend.reship), and the chat shows a grey system note after the agent's
  confirmation (escalation_notes). Neither names the mood.

A late package gets a delay_watch follow-up, so the next visit has a question to read the answer against.
"""

from __future__ import annotations

from datetime import date, timedelta

from bookly import config
from bookly.missions import OPEN, _human

REASON = "lost_in_transit"


def enabled(store) -> bool:
    return bool(store) and config.RESHIP_ENABLED


def lost_on(order, policy) -> date | None:
    """The first day the existing _likely_lost rule says yes for this order (code, exact)."""
    from bookly.tools import _likely_lost

    if not order.eta:
        return None
    d = order.eta
    for _ in range(60):
        d += timedelta(days=1)
        if _likely_lost(order, d, policy):
            return d
    return None


def maybe_open_watch(toolbox, order) -> None:
    """After get_order: a late, not-yet-lost package with nothing open gets a delay_watch follow-up."""
    from bookly.tools import _likely_lost

    store, b = toolbox.store, toolbox.b
    late = order.status == "shipped" and order.eta and b.today > order.eta
    if not late or _likely_lost(order, b.today, toolbox.p) or b.reship_history(order.order_id):
        return
    if any(m.order_id == order.order_id and m.kind == "delay_watch" and m.status in OPEN for m in store.missions.items):
        return
    m = store.missions.open_delay_watch(order, b.today)
    toolbox.s.log("follow_up", mission_id=m.mission_id, to_status=m.status,
                  decision=f"opened by code: late, not lost yet; ask again on {m.due_on.isoformat()}")


def apply_delay_watch_reply(store, session, toolbox, mission, outcome: str) -> str:
    """The delay_watch branch of missions.read_reply. Returns the outcome to record."""
    from bookly.tools import _likely_lost

    if outcome == "close":
        mission.status = "closed_resolved"
        return outcome
    if outcome == "ask":
        mission.asks += 1
        return outcome
    if outcome != "escalate":
        return outcome
    b, policy = store.backend, store.policy
    order = b.orders[mission.order_id]
    if not _likely_lost(order, b.today, policy):
        when = lost_on(order, policy)
        mission.status = "closed_still_missing"
        mission.agent_note = (
            f"the customer says {mission.subject} has still not arrived. The system checked the tracking: the "
            f"package is late, but it is not yet treated as lost. Bookly treats a package as lost when tracking has "
            f"not updated for {int(policy.get('shipping.lost_after_business_days_past_eta'))} business days after "
            f"the estimated delivery date; for this order that is {_human(when) if when else 'not known'}. Tell the "
            "customer this in one or two sentences, with the carrier and tracking number, and say Bookly will check "
            "with them again. Do not ask whether it arrived. Do not open a lost-package hand-off: it is not lost yet.")
        return "still_missing"
    result = request_reship(store, session, toolbox, order)
    if result["status"] == "requested":
        mission.status = "closed_reship_requested"
        mission.agent_note = (
            f"the customer says {mission.subject} has still not arrived, and the order now counts as lost. The system "
            f"has requested a replacement (request {result['request_id']}). Give the customer this message, word for "
            f"word: {result['message_for_customer']} Do not call handoff_to_human, do not call search_policy, and do "
            "not say the replacement has been sent yet.")
        return "reship_requested"
    # A check failed (over the cap, or an earlier reship): the existing lost-package path, a person decides.
    h = toolbox.handoff("lost_package", f"Follow-up {mission.mission_id}: {mission.subject} is lost. No reship: "
                                        f"{result['reason']}.")
    mission.status, mission.ticket_id, mission.message_for_customer = "escalated", h["ticket_id"], h["message_for_customer"]
    return "escalate"


def request_reship(store, session, toolbox, order) -> dict:
    """Code's gate for a reship request. The chat agent cannot call this; it runs from a follow-up read."""
    from bookly.store import session_email
    from bookly.tools import _likely_lost

    b, policy = store.backend, store.policy
    checks = {
        "verified": order.order_id in session.verified_orders,
        "lost": _likely_lost(order, b.today, policy),
        "under_cap": b.order_total(order.order_id) <= policy.approval_cap,
        "no_earlier_reship": not b.reship_history(order.order_id),
    }
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        session.log("reship", order_id=order.order_id, checks=checks, decision=f"no reship request: {', '.join(failed)}")
        return {"status": "refused", "reason": ", ".join(failed)}
    email = session_email(session, b)
    prior = store.contacts.prior(email, session.session_id) if email else None
    priority = bool(prior and prior.mood == "angry")
    cites = sorted({m.opened_on.isoformat() for m in store.missions.items
                    if m.order_id == order.order_id and m.kind == "delay_watch"})
    req = b.add_reship_request(order.order_id, REASON, priority, cites)
    session.log("reship", order_id=order.order_id, checks=checks, request_id=req.request_id, priority=priority,
                decision=f"reship request {req.request_id} written by code"
                         + ("; priority flag set (last visit ended angry): a person follows up by email" if priority else ""))
    if priority and toolbox.return_contact and toolbox.return_contact.get("outcome") == "early_escalation":
        # The person who follows up replaces the chat offer of a person. Entitlement is unchanged.
        toolbox.return_contact = {**toolbox.return_contact, "first": None, "later": None}
        toolbox.escalate_early = False
    message = store.kb.message("reship_requested", order_id=order.order_id,
                               last_scan=_human(order.last_scan_at or order.eta), title=order.items[0].title)
    return {"status": "requested", "request_id": req.request_id, "priority": priority, "message_for_customer": message}


def visits_line(cites: list[str]) -> str:
    days = [_human(date.fromisoformat(c)) for c in cites]
    if not days:
        return ""
    if len(days) == 1:
        return f"You first told us about this on {days[0]}."
    return f"You first told us about this on {days[0]}, and again on {', '.join(days[1:])}."


def facts(toolbox) -> list[str]:
    """FACTS SO FAR lines about reships for this conversation's verified orders. Every word is code's."""
    b, lines = toolbox.b, []
    for req in b.reship_requests:
        if req.order_id not in toolbox.s.verified_orders:
            continue
        order = b.orders[req.order_id]
        if req.status == "pending":
            lines.append(f"- Reship request {req.request_id} for order {req.order_id} is waiting for Bookly's team. "
                         "Do not say the replacement has been sent.")
            continue
        rs = next(r for r in b.reships if r.reship_id == req.reship_id)
        for m in toolbox.store.missions.items:  # the earlier "not sent yet" note is out of date now
            if m.order_id == req.order_id and m.status == "closed_reship_requested":
                m.agent_note = (f"the system requested a replacement for {m.subject}, and it has now been sent. "
                                "Use the Reship line.")
                m.ticket_id = m.ticket_id or rs.ticket_id  # the store panel shows the staff follow-up ticket
        message = toolbox.kb.message(
            "reship_done", title=order.items[0].title, reship_id=rs.reship_id, visits_line=visits_line(req.cites),
            priority_line=toolbox.kb.message("reship_priority_line") if rs.priority else "")
        lines.append(f"- Reship {rs.reship_id} for order {req.order_id} was processed in Bookly's order console on "
                     f"{_human(date.fromisoformat(rs.done_on))}. If you have not yet, give the customer this message, "
                     f"word for word, before anything else: {message}")
    return lines


def escalation_notes(toolbox, reply: str) -> list[str]:
    """Grey system notes for the chat, written by code: one per priority reship, shown once, on the turn whose
    reply relays the confirmation (it names the reship id). They say a person was brought in, never why."""
    notes = []
    for rs in toolbox.b.reships:
        if (rs.ticket_id and rs.order_id in toolbox.s.verified_orders and rs.reship_id in reply
                and rs.reship_id not in toolbox.escalation_noted):
            toolbox.escalation_noted.add(rs.reship_id)
            note = f"Escalated to staff · priority follow-up · ticket {rs.ticket_id} · reship {rs.reship_id}"
            toolbox.s.log("reship", order_id=rs.order_id, decision=f"note shown in the chat: {note}")
            notes.append(note)
    return notes
