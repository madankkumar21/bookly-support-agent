"""Mock Bookly systems: order lookup, the returns ledger, password resets and the helpdesk queue.

In production these are Bookly's order API, payments/refunds API and helpdesk. Here they are
in-memory, so each conversation (and each eval run) starts from the same clean state.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from bookly import config
from bookly.config import ORDERS_PATH, TODAY


@dataclass(frozen=True)
class Item:
    item_id: str
    title: str
    format: str  # "print" | "ebook"
    price: float
    downloaded: bool = False


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_name: str
    email: str
    status: str  # "processing" | "shipped" | "delivered"
    placed_at: date
    items: tuple[Item, ...]
    shipped_at: date | None = None
    delivered_at: date | None = None
    carrier: str | None = None
    tracking_number: str | None = None
    eta: date | None = None
    last_scan_at: date | None = None

    def item(self, item_id: str) -> Item | None:
        return next((i for i in self.items if i.item_id == item_id), None)


@dataclass
class ReturnRecord:
    rma_id: str
    refund_id: str
    quote_id: str
    order_id: str
    item_ids: list[str]
    reason: str
    resolution: str  # "refund_no_return" | "return_for_refund"
    amount: float
    label_url: str | None
    created_on: str


@dataclass
class Ticket:
    ticket_id: str
    reason_code: str
    payload: dict
    opened_on: str | None = None  # ISO dates, so the snapshot stays plain JSON
    answered_on: str | None = None  # set when a person replies (the demo's "Staff replied" button)
    escalated_to: str | None = None  # a later priority ticket that took this one over (bookly/contact.py)
    staff_reply: str | None = None  # what the person wrote, when the staff panel sent text with the reply


@dataclass
class ReshipRequest:
    """Written only by code (bookly/reship.py) after its checks pass. The order console acts on it."""
    request_id: str
    order_id: str
    reason_code: str  # lost_in_transit
    requested_on: str
    priority: bool  # the customer's last visit ended angry: a person follows up by email
    cites: list[str]  # ISO dates of the customer's earlier contacts about this order (from follow-up records)
    status: str = "pending"  # pending | done
    reship_id: str | None = None
    contacts: list[dict] = field(default_factory=list)  # {"on": ISO date, "fact": code-known fact} per visit, oldest first


@dataclass
class Reship:
    reship_id: str
    order_id: str
    request_id: str
    reason_code: str
    done_on: str
    priority: bool
    via: str = "order_console"
    ticket_id: str | None = None  # priority only: the staff follow-up ticket code opened with the reship


class ItemAlreadyReturned(Exception):
    """A second return for a book that already has one. The gate refuses this first; this is the last line of
    defence when two conversations share one backend (bookly/store.py) and act at the same moment."""


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def normalize_order_id(raw: str) -> str | None:
    """Accept 'BK-1001', 'bk1001', '#1001' or '1001'. Return the canonical 'BK-1001' or None."""
    digits = re.findall(r"\d+", raw or "")
    if len(digits) != 1:
        return None
    return f"BK-{digits[0]}"


@dataclass
class Backend:
    orders: dict[str, Order]
    ledger: list[ReturnRecord] = field(default_factory=list)
    password_resets: list[str] = field(default_factory=list)
    tickets: list[Ticket] = field(default_factory=list)
    today: date = TODAY
    reship_requests: list[ReshipRequest] = field(default_factory=list)  # BOOKLY_RESHIP=1 only
    reships: list[Reship] = field(default_factory=list)
    console_posts: list[dict] = field(default_factory=list)  # every reship POST the console sent, accepted or not
    _lock: Any = field(default_factory=threading.Lock, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path = ORDERS_PATH, today: date = TODAY) -> Backend:
        raw = json.loads(Path(path).read_text())
        orders: dict[str, Order] = {}
        for o in raw["orders"]:
            items = tuple(
                Item(
                    item_id=i["item_id"],
                    title=i["title"],
                    format=i["format"],
                    price=float(i["price"]),
                    downloaded=bool(i.get("downloaded", False)),
                )
                for i in o["items"]
            )
            orders[o["order_id"]] = Order(
                order_id=o["order_id"],
                customer_name=o["customer_name"],
                email=o["email"].lower(),
                status=o["status"],
                placed_at=_d(o["placed_at"]),
                items=items,
                shipped_at=_d(o.get("shipped_at")),
                delivered_at=_d(o.get("delivered_at")),
                carrier=o.get("carrier"),
                tracking_number=o.get("tracking_number"),
                eta=_d(o.get("eta")),
                last_scan_at=_d(o.get("last_scan_at")),
            )
        return cls(orders=orders, today=today)

    # ---- orders -------------------------------------------------------------------------
    def find_order(self, order_id: str) -> Order | None:
        canonical = normalize_order_id(order_id)
        return self.orders.get(canonical) if canonical else None

    def lookup(self, order_id: str, email: str) -> Order | None:
        """Return the order only if the email matches. A wrong email and an unknown order look the same."""
        order = self.find_order(order_id)
        if order is None or order.email != (email or "").strip().lower():
            return None
        return order

    # ---- returns ledger -----------------------------------------------------------------
    def returned_item_ids(self, order_id: str) -> dict[str, str]:
        """item_id -> rma_id for items that already have a return."""
        out: dict[str, str] = {}
        for rec in self.ledger:
            if rec.order_id == order_id:
                for item_id in rec.item_ids:
                    out[item_id] = rec.rma_id
        return out

    def find_return_by_quote(self, quote_id: str) -> ReturnRecord | None:
        return next((r for r in self.ledger if r.quote_id == quote_id), None)

    def record_return(
        self, *, quote_id: str, order_id: str, item_ids: list[str], reason: str, resolution: str, amount: float
    ) -> ReturnRecord:
        with self._lock:  # check and write as one step
            existing = self.find_return_by_quote(quote_id)
            if existing:  # the ledger is unique on quote_id: a retry can never refund twice
                return existing
            already = self.returned_item_ids(order_id)
            if any(item_id in already for item_id in item_ids):  # one book, one return, whichever chat asks
                raise ItemAlreadyReturned(order_id)
            n = len(self.ledger) + 1
            digits = order_id.split("-")[-1]
            rec = ReturnRecord(
                rma_id=f"RMA-{digits}-{n:02d}",
                refund_id=f"RF-{digits}-{n:02d}",
                quote_id=quote_id,
                order_id=order_id,
                item_ids=list(item_ids),
                reason=reason,
                resolution=resolution,
                amount=round(amount, 2),
                label_url=(f"https://bookly.example/labels/RMA-{digits}-{n:02d}.pdf" if resolution == "return_for_refund" else None),
                created_on=self.today.isoformat(),
            )
            self.ledger.append(rec)
            return rec

    # ---- account and helpdesk -----------------------------------------------------------
    def send_password_reset(self, email: str) -> None:
        """Record every request. A real mailer sends a link only to accounts that exist; recording all of
        them keeps the record from revealing which emails have accounts."""
        self.password_resets.append(email.strip().lower())

    def create_ticket(self, reason_code: str, payload: dict) -> Ticket:
        ticket = Ticket(ticket_id=f"T-{len(self.tickets) + 1:04d}", reason_code=reason_code, payload=payload,
                        opened_on=self.today.isoformat())
        self.tickets.append(ticket)
        return ticket

    # ---- reships (BOOKLY_RESHIP=1) ---------------------------------------------------------
    def order_total(self, order_id: str) -> float:
        return round(sum(i.price for i in self.orders[order_id].items), 2)

    def reship_history(self, order_id: str) -> list:
        return [r for r in self.reship_requests if r.order_id == order_id] + [r for r in self.reships if r.order_id == order_id]

    def add_reship_request(self, order_id: str, reason_code: str, priority: bool, cites: list[str],
                           contacts: list[dict] | None = None) -> ReshipRequest:
        """Called only by bookly/reship.py, after its checks. One request per order, ever."""
        with self._lock:
            if self.reship_history(order_id):
                raise ValueError(f"{order_id} already has a reship request or a reship")
            req = ReshipRequest(request_id=f"RR-{len(self.reship_requests) + 1:04d}", order_id=order_id,
                                reason_code=reason_code, requested_on=self.today.isoformat(), priority=priority,
                                cites=list(cites), contacts=[dict(c) for c in contacts or []])
            self.reship_requests.append(req)
            return req

    def reship(self, order_id: str, reason_code: str, cap: float) -> dict:
        """The order console's Reship action. It acts only on a request that code wrote first.

        Rejects: an order with no pending request, a second reship of the same order, an order over the cap,
        and a reason code that differs from the request's. Every call is recorded in console_posts."""
        with self._lock:
            canonical = normalize_order_id(order_id) or str(order_id)
            pending = next((r for r in self.reship_requests if r.order_id == canonical and r.status == "pending"), None)
            if any(r.order_id == canonical for r in self.reships):
                result = {"status": "rejected", "reason": "already_reshipped"}
            elif pending is None:
                result = {"status": "rejected", "reason": "no_pending_request"}
            elif canonical not in self.orders or self.order_total(canonical) > cap:
                result = {"status": "rejected", "reason": "over_value_cap"}
            elif reason_code != pending.reason_code:
                result = {"status": "rejected", "reason": "reason_code_mismatch", "expected": pending.reason_code}
            else:
                digits = canonical.split("-")[-1]
                rs = Reship(reship_id=f"RS-{digits}-{len(self.reships) + 1:02d}", order_id=canonical,
                            request_id=pending.request_id, reason_code=reason_code, done_on=self.today.isoformat(),
                            priority=pending.priority)
                self.reships.append(rs)
                pending.status, pending.reship_id = "done", rs.reship_id
                if rs.priority:  # code, not the model: a person follows up on a priority reship
                    rs.ticket_id = self._reship_followup_ticket(rs, pending).ticket_id
                result = {"status": "reshipped", "reship_id": rs.reship_id, "priority": rs.priority,
                          **({"ticket_id": rs.ticket_id} if rs.ticket_id else {})}
            self.console_posts.append({"order_id": canonical, "reason_code": reason_code, "on": self.today.isoformat(),
                                       **result})
            return result

    def _reship_followup_ticket(self, rs: Reship, req: ReshipRequest) -> Ticket:
        """The staff ticket for a priority reship. Called inside reship(), under the lock."""
        earlier = ", ".join(req.cites) or "none on file"
        return self.create_ticket("reship_followup", {
            "reason_code": "reship_followup", "priority": True, "identity": f"opened by code with reship {rs.reship_id}",
            "order_id": rs.order_id, "reship_id": rs.reship_id, "request_id": req.request_id,
            "earlier_contacts": list(req.cites),
            "summary": (f"Priority follow-up: reship {rs.reship_id} for {rs.order_id} was sent on {rs.done_on} "
                        f"(request {req.request_id}). Earlier contacts about this order: {earlier}. "
                        "Check in with the customer by email."),
            "handoff": self._handoff_summary(rs, req),
        })

    def _handoff_summary(self, rs: Reship, req: ReshipRequest) -> dict:
        """What staff read first on a priority reship_followup ticket. Built by code from stored records only:
        the order, the per-visit facts on the request, and the reship. No model text and no mood."""
        md = lambda iso: f"{date.fromisoformat(iso).month}/{date.fromisoformat(iso).day}"  # noqa: E731
        name = self.orders[rs.order_id].customer_name if rs.order_id in self.orders else "customer"
        return {
            "header": f"{rs.order_id} · {name} · Priority follow-up",
            "contacts": [f"{md(c['on'])} — {c['fact']}" for c in req.contacts],
            "done": f"Reship {rs.reship_id} issued in the order console on {md(rs.done_on)}.",
            "next": "Confirm the replacement shipped, then check in with the customer.",
        }

    def snapshot(self) -> dict:
        """End state used by the eval checks."""
        out = {
            "returns": [asdict(r) for r in self.ledger],
            "password_resets": list(self.password_resets),
            "tickets": [asdict(t) for t in self.tickets],
        }
        if config.RESHIP_ENABLED:  # with the flag off the snapshot keeps its old shape
            out.update(reship_requests=[asdict(r) for r in self.reship_requests],
                       reships=[asdict(r) for r in self.reships], console_posts=[dict(p) for p in self.console_posts])
        return out
