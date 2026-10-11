"""The return-eligibility engine. Deterministic: same order, items, reason and date -> same decision.

The model never decides eligibility or amounts. It supplies the customer's reason and the items;
this module applies the values in policy.yaml and returns a decision the gate can trust.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from bookly.backend import Order
from bookly.config import POLICY_PATH

REASONS = {
    "damaged": "The book arrived damaged",
    "wrong_item": "We sent the wrong book",
    "changed_mind": "The customer no longer wants it (did not like it, bought by mistake, duplicate gift)",
}


@dataclass(frozen=True)
class Policy:
    raw: dict

    @classmethod
    def load(cls, path: Path = POLICY_PATH, overrides: dict[str, Any] | None = None) -> "Policy":
        raw = yaml.safe_load(Path(path).read_text())
        raw = copy.deepcopy(raw)
        for dotted, value in (overrides or {}).items():
            node = raw
            *parents, leaf = dotted.split(".")
            for key in parents:
                node = node[key]
            if leaf not in node:
                raise KeyError(f"Unknown policy key: {dotted}")
            node[leaf] = type(node[leaf])(value)
        return cls(raw=raw)

    def get(self, dotted: str) -> Any:
        node: Any = self.raw
        for key in dotted.split("."):
            node = node[key]
        return node

    @property
    def version(self) -> str:
        return str(self.raw.get("version", "unversioned"))

    @property
    def print_window(self) -> int:
        return int(self.get("returns.print_return_window_days"))

    @property
    def damaged_window(self) -> int:
        return int(self.get("returns.damaged_window_days"))

    @property
    def ebook_window(self) -> int:
        return int(self.get("returns.ebook_refund_window_days"))

    @property
    def approval_cap(self) -> float:
        return float(self.get("returns.human_approval_over_usd"))


@dataclass
class Line:
    item_id: str
    title: str
    format: str
    resolution: str  # "refund_no_return" | "return_for_refund"
    amount: float


@dataclass
class Rejected:
    item_id: str
    title: str
    reason_code: str
    detail: str


@dataclass
class Decision:
    decision: str  # refund_no_return | return_for_refund | needs_human | ineligible | needs_input
    reason: str | None
    reason_code: str
    lines: list[Line] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)
    amount: float = 0.0
    policy_ref: str = ""
    needs_field: str | None = None
    options: list[dict] = field(default_factory=list)

    @property
    def refundable(self) -> bool:
        return self.decision in ("refund_no_return", "return_for_refund")

    def to_dict(self) -> dict:
        return asdict(self)


def _needs_reason() -> Decision:
    return Decision(
        decision="needs_input",
        reason=None,
        reason_code="reason_missing",
        needs_field="reason",
        options=[{"value": k, "label": v} for k, v in REASONS.items()],
        policy_ref="returns",
    )


def evaluate(
    order: Order,
    item_ids: list[str] | None,
    reason: str | None,
    today: date,
    policy: Policy,
    already_returned: dict[str, str] | None = None,
) -> Decision:
    """Decide what Bookly can offer for these items. Pure function: no I/O, no model."""
    already_returned = already_returned or {}

    if reason not in REASONS:
        return _needs_reason()

    # Which items? A single-item order needs no question. A multi-item order must name the items.
    if not item_ids:
        if len(order.items) == 1:
            item_ids = [order.items[0].item_id]
        else:
            return Decision(
                decision="needs_input",
                reason=reason,
                reason_code="item_missing",
                needs_field="item_ids",
                options=[
                    {"item_id": i.item_id, "title": i.title, "price": i.price, "already_returned": i.item_id in already_returned}
                    for i in order.items
                ],
                policy_ref="returns",
            )

    unknown = [i for i in item_ids if order.item(i) is None]
    if unknown:
        return Decision(
            decision="needs_input",
            reason=reason,
            reason_code="unknown_item",
            needs_field="item_ids",
            options=[{"item_id": i.item_id, "title": i.title, "price": i.price} for i in order.items],
            policy_ref="returns",
        )

    lines: list[Line] = []
    rejected: list[Rejected] = []
    refs: set[str] = set()

    for item_id in dict.fromkeys(item_ids):  # de-duplicate, keep order
        item = order.item(item_id)
        assert item is not None
        if item_id in already_returned:
            rejected.append(Rejected(item_id, item.title, "already_returned", f"Return {already_returned[item_id]} already exists for this item."))
            continue

        if item.format == "ebook":
            refs.add("returns.ebook_refund_window_days")
            age = (today - order.placed_at).days
            if item.downloaded:
                rejected.append(Rejected(item_id, item.title, "ebook_downloaded", "The ebook has been downloaded."))
            elif age > policy.ebook_window:
                rejected.append(Rejected(item_id, item.title, "outside_ebook_window", f"Purchased {age} days ago."))
            else:
                lines.append(Line(item_id, item.title, item.format, "refund_no_return", item.price))
            continue

        # Print books.
        if order.status != "delivered" or order.delivered_at is None:
            rejected.append(Rejected(item_id, item.title, "not_delivered", f"Order status is {order.status}."))
            continue
        age = (today - order.delivered_at).days
        if reason in ("damaged", "wrong_item"):
            refs.add("returns.damaged_window_days")
            if age <= policy.damaged_window:
                lines.append(Line(item_id, item.title, item.format, "refund_no_return", item.price))
            else:
                rejected.append(Rejected(item_id, item.title, "outside_damage_window", f"Delivered {age} days ago."))
        else:  # changed_mind
            refs.add("returns.print_return_window_days")
            if age <= policy.print_window:
                lines.append(Line(item_id, item.title, item.format, "return_for_refund", item.price))
            else:
                rejected.append(Rejected(item_id, item.title, "outside_return_window", f"Delivered {age} days ago."))

    policy_ref = f"policy {policy.version}: " + ", ".join(sorted(refs)) if refs else f"policy {policy.version}"

    if not lines:
        codes = {r.reason_code for r in rejected}
        return Decision(
            decision="ineligible",
            reason=reason,
            reason_code=codes.pop() if len(codes) == 1 else "mixed",
            rejected=rejected,
            policy_ref=policy_ref,
        )

    amount = round(sum(line.amount for line in lines), 2)
    if amount > policy.approval_cap:
        return Decision(
            decision="needs_human",
            reason=reason,
            reason_code="over_approval_limit",
            lines=lines,
            rejected=rejected,
            amount=amount,
            policy_ref=f"policy {policy.version}: returns.human_approval_over_usd",
        )

    resolution = "refund_no_return" if all(l.resolution == "refund_no_return" for l in lines) else "return_for_refund"
    return Decision(
        decision=resolution,
        reason=reason,
        reason_code="eligible",
        lines=lines,
        rejected=rejected,
        amount=amount,
        policy_ref=policy_ref,
    )
