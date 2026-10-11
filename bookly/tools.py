"""Purpose-built tools the model can call. Reads are separate from writes; every write passes the gate.

Each tool: name(inputs) -> {status enum, ..., ts}. Descriptions are written for the model, because
under-described tools were the most common cause of wrong tool use in earlier builds.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from bookly import config
from bookly.backend import Backend, normalize_order_id
from bookly.gate import check_create_return
from bookly.kb import PolicyText
from bookly.policy import Policy, evaluate
from bookly.state import Action, Session


def _obj(properties: dict, description: str, name: str) -> dict:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TOOLS: list[dict] = sorted(
    [
        _obj(
            {
                "order_id": {"type": "string", "description": "The Bookly order number the customer gave, e.g. BK-1001."},
                "email": {"type": "string", "description": "The email address the customer says is on the order."},
            },
            "Look up an order. Needs BOTH the order number and the email on the order; this is how the customer is "
            "verified. Returns status 'found' with the order (status, dates, carrier, tracking, items with item_id, "
            "days_since_delivery, likely_lost) or 'no_match'. 'no_match' means the number and email do not match an "
            "order; it does not say which one is wrong, on purpose. Call this before discussing any order details.",
            "get_order",
        ),
        _obj(
            {
                "order_id": {"type": "string", "description": "A verified order number (get_order returned found)."},
                "item_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "item_id values from get_order for the books to return. Use an empty list if the order "
                    "has several books and the customer has not said which; the result then lists the choices.",
                },
                "reason": {
                    "type": "string",
                    "enum": ["damaged", "wrong_item", "changed_mind", "unknown"],
                    "description": "The customer's reason in their own words, mapped: damaged = physically damaged; "
                    "wrong_item = a different book than ordered; changed_mind = no longer wants it (did not like it, bought "
                    "by mistake, duplicate). Use unknown if they have not said; the result then asks for it.",
                },
            },
            "Ask Bookly's policy engine what can be offered for a return or refund. Read-only: it changes nothing. "
            "Decisions: refund_no_return, return_for_refund (both include a quote_id, amount and the exact terms), "
            "ineligible (with the reason), needs_human (a person must approve), needs_input (a missing field and its "
            "options). Each new check replaces any earlier quote. You never decide eligibility or amounts yourself.",
            "check_return_eligibility",
        ),
        _obj(
            {"quote_id": {"type": "string", "description": "The quote_id from the latest check_return_eligibility result."}},
            "Create the return and issue the refund for a quote. Only works after the customer has confirmed that exact "
            "quote on the confirmation card (a FACTS SO FAR message will say so). Returns 'created' with rma_id, "
            "refund_id, amount and label_url (if the book must be sent back), 'already_exists' with the same references "
            "if this quote was already used, or 'blocked' with the reason and what to do next.",
            "create_return",
        ),
        _obj(
            {"topic": {"type": "string", "description": "The customer's question in a few words, e.g. 'shipping to Canada'."}},
            "Search Bookly's official policy text (returns, refunds, shipping, lost packages, password resets). Returns "
            "passages to answer from. An empty list means Bookly has no policy text on this topic: say you do not have "
            "that information and offer a person.",
            "search_policy",
        ),
        _obj(
            {"email": {"type": "string", "description": "The email address on the customer's Bookly account."}},
            "Send a password reset link to the account email. Never ask for the customer's password. Returns the exact "
            "message to give the customer; it is the same whether or not an account exists, so nobody can test which "
            "emails have accounts.",
            "send_password_reset",
        ),
        _obj(
            {
                "reason_code": {
                    "type": "string",
                    "enum": [
                        "customer_request", "needs_human_approval", "policy_exception_request", "lost_package",
                        "tool_failure", "legal_or_abuse", "cannot_help",
                    ],
                    "description": "Why a person is needed.",
                },
                "summary": {"type": "string", "description": "Two or three factual sentences for the person who picks this up: what the customer wants, what was checked, what was offered."},
            },
            "Hand the conversation to a member of Bookly's team. The system attaches the verified order, the latest "
            "quote and every action taken, so the customer never repeats themselves. Returns a ticket_id and the exact "
            "message to give the customer.",
            "handoff_to_human",
        ),
    ],
    key=lambda t: t["name"],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _business_days_between(start: date, end: date) -> int:
    days, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


NEXT_STEP_FOR_BLOCK = {
    "awaiting_customer_confirmation": "The customer has not confirmed this quote yet. Ask them to review the terms and confirm on the card.",
    "terms_not_shown_to_customer": "The customer has not seen the confirmation card yet. Summarize the offer in a sentence or two and ask them to confirm on the card; the system shows it at the end of your message.",
    "customer_declined": "The customer declined. Do not create a return. Ask what they would like instead.",
    "stale_quote": "That quote was replaced. Use the quote_id from the latest check_return_eligibility result.",
    "unknown_quote": "Use the quote_id returned by check_return_eligibility.",
    "not_verified": "Verify the order first: ask for the order number and email, then call get_order.",
    "needs_human_approval": "A person must approve this refund. Call handoff_to_human with reason_code needs_human_approval.",
    "not_eligible": "This quote is not refundable. Explain why and offer a person.",
    "already_returned": "These books already have a return. Give the customer the existing references.",
}


class Toolbox:
    def __init__(self, session: Session, backend: Backend, policy: Policy, policy_text: PolicyText):
        self.s, self.b, self.p, self.kb = session, backend, policy, policy_text
        self.lookup_misses = 0

    def run(self, name: str, args: dict[str, Any]) -> tuple[dict, bool]:
        """Execute one tool call. Returns (result, is_error). Never raises into the model loop."""
        handler = getattr(self, f"_t_{name}", None)
        if handler is None:
            return {"status": "error", "reason": f"unknown tool {name}"}, True
        try:
            result = handler(**args)
        except Exception as exc:  # a broken tool must not crash the conversation
            self.s.log("tool_error", tool=name, error=repr(exc))
            return {"status": "failed", "reason": "internal_error", "next_step": "Apologize and try once more; if it fails again, hand off to a person."}, True
        result.setdefault("ts", _now())
        return result, False

    # ---- reads --------------------------------------------------------------------------
    def _t_get_order(self, order_id: str, email: str) -> dict:
        order = self.b.lookup(order_id, email)
        if order is None:
            self.lookup_misses += 1
            out = {"status": "no_match", "misses_this_conversation": self.lookup_misses}
            if self.lookup_misses >= 2:
                out["next_step"] = "Two lookups have failed. Offer to connect the customer with a person."
            return out
        self.s.verified_orders[order.order_id] = order.customer_name
        returned = self.b.returned_item_ids(order.order_id)
        today = self.b.today
        likely_lost = bool(
            order.status == "shipped" and order.eta and today > order.eta
            and _business_days_between(order.eta, today) >= int(self.p.get("shipping.lost_after_business_days_past_eta"))
        )
        return {
            "status": "found",
            "today": today.isoformat(),
            "order": {
                "order_id": order.order_id,
                "customer_first_name": order.customer_name.split()[0],
                "status": order.status,
                "placed_at": order.placed_at.isoformat(),
                "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
                "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
                "carrier": order.carrier,
                "tracking_number": order.tracking_number,
                "estimated_delivery": order.eta.isoformat() if order.eta else None,
                "days_since_delivery": (today - order.delivered_at).days if order.delivered_at else None,
                "likely_lost": likely_lost,
                "items": [
                    {"item_id": i.item_id, "title": i.title, "format": i.format, "price": i.price,
                     "ebook_downloaded": i.downloaded if i.format == "ebook" else None,
                     "return_on_file": returned.get(i.item_id)}
                    for i in order.items
                ],
            },
        }

    def _t_check_return_eligibility(self, order_id: str, item_ids: list[str], reason: str) -> dict:
        canonical = normalize_order_id(order_id)
        if canonical not in self.s.verified_orders:
            return {"status": "blocked", "reason": "not_verified", "next_step": NEXT_STEP_FOR_BLOCK["not_verified"]}
        order = self.b.find_order(canonical)
        d = evaluate(order, item_ids, None if reason == "unknown" else reason, self.b.today, self.p,
                     self.b.returned_item_ids(order.order_id))

        if d.refundable:
            q = self.s.issue_quote(order.order_id, d.reason, d, self.kb.terms(d))
            return {
                "status": "ok",
                "decision": d.decision,
                "quote_id": q.quote_id,
                "reason": d.reason,
                "books": [line.title for line in d.lines],
                "amount": d.amount,
                "terms": q.terms,
                "not_included": [{"title": r.title, "why": r.reason_code} for r in d.rejected],
                "policy_ref": d.policy_ref,
                "next_step": "Summarize this offer in a sentence or two and ask the customer to review and confirm on the "
                             "card the system shows. Do not call create_return until FACTS SO FAR says they confirmed.",
            }

        self.s.void_open_quotes()
        if d.decision == "needs_input":
            field = d.needs_field or "unknown"
            self.s.needs_input_counts[field] = self.s.needs_input_counts.get(field, 0) + 1
            out = {"status": "ok", "decision": "needs_input", "field": field, "options": d.options,
                   "next_step": f"Ask the customer for: {field}. Offer the options as buttons."}
            if self.s.needs_input_counts[field] > config.MAX_NEEDS_INPUT_PER_FIELD:
                out["next_step"] = "This has been asked too many times. Offer to connect the customer with a person."
                out["handoff_required"] = True
            return out
        if d.decision == "needs_human":
            return {"status": "ok", "decision": "needs_human", "reason_code": d.reason_code, "amount": d.amount,
                    "approval_limit": self.p.approval_cap, "books": [line.title for line in d.lines],
                    "next_step": "Explain that refunds above the approval limit are reviewed by a person, then call "
                                 "handoff_to_human with reason_code needs_human_approval."}
        return {
            "status": "ok",
            "decision": "ineligible",
            "reason_code": d.reason_code,
            "explanation": self._explain(d),
            "policy_ref": d.policy_ref,
            "next_step": "Explain this plainly and kindly. Do not offer exceptions. Offer a person who can review it.",
        }

    def _explain(self, d) -> list[str]:
        rules = {
            "outside_return_window": f"Change-of-mind returns are accepted within {self.p.print_window} days of delivery.",
            "outside_damage_window": f"Damaged or wrong items must be reported within {self.p.damaged_window} days of delivery.",
            "outside_ebook_window": f"Ebooks can be refunded within {self.p.ebook_window} days of purchase.",
            "ebook_downloaded": "Ebooks cannot be refunded once they have been downloaded.",
            "not_delivered": "A book can be returned once it has been delivered.",
            "already_returned": "This book already has a return.",
        }
        return [f"{r.title}: {rules.get(r.reason_code, r.reason_code)} {r.detail}".strip() for r in d.rejected]

    def _t_search_policy(self, topic: str) -> dict:
        passages = self.kb.search(topic)
        if not passages:
            return {"status": "ok", "passages": [],
                    "next_step": "No policy text covers this. Say you do not have that information and offer a person."}
        return {"status": "ok", "passages": [{"id": p.id, "title": p.title, "text": p.text} for p in passages]}

    # ---- writes -------------------------------------------------------------------------
    def _t_create_return(self, quote_id: str) -> dict:
        gate = check_create_return(self.s, self.b, self.p, quote_id)
        self.s.log("gate", tool="create_return", quote_id=quote_id, allowed=gate.allowed, status=gate.status, reason=gate.reason)
        if gate.status == "already_exists":
            r = gate.existing
            return {"status": "already_exists", "rma_id": r.rma_id, "refund_id": r.refund_id, "amount": r.amount,
                    "label_url": r.label_url, "next_step": "Do not create it again. Give the customer these references."}
        if not gate.allowed:
            return {"status": "blocked", "reason": gate.reason, "next_step": NEXT_STEP_FOR_BLOCK.get(gate.reason, "Explain and offer a person.")}

        q = self.s.quotes[quote_id]
        rec = self.b.record_return(
            quote_id=q.quote_id, order_id=q.order_id, item_ids=[line.item_id for line in q.decision.lines],
            reason=q.reason, resolution=q.decision.decision, amount=q.decision.amount,
        )
        q.status = "used"
        self.s.actions.append(Action("return_created", rec.rma_id, {"refund_id": rec.refund_id, "amount": rec.amount, "quote_id": q.quote_id}))
        return {
            "status": "created", "rma_id": rec.rma_id, "refund_id": rec.refund_id, "amount": rec.amount,
            "resolution": rec.resolution, "label_url": rec.label_url,
            "refund_timing_business_days": int(self.p.get("returns.refund_business_days")),
        }

    def _t_send_password_reset(self, email: str) -> dict:
        if "@" not in (email or ""):
            return {"status": "invalid_email", "next_step": "Ask for the full email address on the account."}
        self.b.send_password_reset(email)
        self.s.actions.append(Action("password_reset_requested", email.strip().lower(), {}))
        return {"status": "sent", "message_for_customer": self.kb.message("password_reset")}

    def _t_handoff_to_human(self, reason_code: str, summary: str) -> dict:
        return self.handoff(reason_code, summary)

    def handoff(self, reason_code: str, summary: str) -> dict:
        """Also called directly by the orchestrator (turn cap, repeated tool failure). One ticket per conversation."""
        if self.s.handoff:
            return {"status": "queued", "ticket_id": self.s.handoff["ticket_id"],
                    "message_for_customer": self.kb.message("handoff", ticket_id=self.s.handoff["ticket_id"])}
        q = self.s.latest_quote()
        payload = {
            "reason_code": reason_code,
            "summary": summary,
            "identity": ("verified: " + ", ".join(f"{o} ({n})" for o, n in self.s.verified_orders.items())) if self.s.verified_orders else "not verified",
            "latest_quote": ({"quote_id": q.quote_id, "order_id": q.order_id, "decision": q.decision.decision,
                              "reason": q.reason, "amount": q.decision.amount, "status": q.status} if q else None),
            "actions": [{"kind": a.kind, "ref": a.ref, **a.detail} for a in self.s.actions],
            "turn": self.s.turn,
        }
        ticket = self.b.create_ticket(reason_code, payload)
        self.s.handoff = {"ticket_id": ticket.ticket_id, "reason_code": reason_code}
        self.s.actions.append(Action("handoff", ticket.ticket_id, {"reason_code": reason_code}))
        return {"status": "queued", "ticket_id": ticket.ticket_id,
                "message_for_customer": self.kb.message("handoff", ticket_id=ticket.ticket_id)}


def result_json(result: dict) -> str:
    return json.dumps(result, sort_keys=True, default=str)
