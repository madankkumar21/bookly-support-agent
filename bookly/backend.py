"""Mock Bookly systems: order lookup, the returns ledger, password resets and the helpdesk queue.

In production these are Bookly's order API, payments/refunds API and helpdesk. Here they are
in-memory, so each conversation (and each eval run) starts from the same clean state.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

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

    @classmethod
    def load(cls, path: Path = ORDERS_PATH, today: date = TODAY) -> "Backend":
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

    def known_email(self, email: str) -> bool:
        e = (email or "").strip().lower()
        return any(o.email == e for o in self.orders.values())

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
        existing = self.find_return_by_quote(quote_id)
        if existing:  # the ledger is unique on quote_id: a retry can never refund twice
            return existing
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
        if self.known_email(email):
            self.password_resets.append(email.strip().lower())

    def create_ticket(self, reason_code: str, payload: dict) -> Ticket:
        ticket = Ticket(ticket_id=f"T-{len(self.tickets) + 1:04d}", reason_code=reason_code, payload=payload)
        self.tickets.append(ticket)
        return ticket

    def snapshot(self) -> dict:
        """End state used by the eval checks."""
        return {
            "returns": [asdict(r) for r in self.ledger],
            "password_resets": list(self.password_resets),
            "tickets": [asdict(t) for t in self.tickets],
        }
