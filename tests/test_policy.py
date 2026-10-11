"""The eligibility engine owns the hard policy cases. No model, no network."""

import pytest

from bookly.policy import Policy, evaluate


def ev(backend, policy, today, order_id, reason, item_ids=None):
    order = backend.find_order(order_id)
    return evaluate(order, item_ids, reason, today, policy, backend.returned_item_ids(order.order_id))


def test_damaged_within_window_is_refund_without_return(backend, policy, today):
    d = ev(backend, policy, today, "BK-1001", "damaged")
    assert d.decision == "refund_no_return"
    assert d.amount == 18.99
    assert [line.item_id for line in d.lines] == ["BK-1001-1"]


def test_h1_day_30_is_eligible(backend, policy, today):
    d = ev(backend, policy, today, "BK-1004", "changed_mind")  # delivered 2026-09-10, today 2026-10-10
    assert d.decision == "return_for_refund"
    assert d.amount == 17.25


def test_h1_day_31_is_not_eligible(backend, policy, today):
    d = ev(backend, policy, today, "BK-1003", "changed_mind")  # delivered 2026-09-09
    assert d.decision == "ineligible"
    assert d.reason_code == "outside_return_window"
    assert not d.lines


def test_h3_multi_item_order_without_items_asks_which(backend, policy, today):
    d = ev(backend, policy, today, "BK-1002", "changed_mind")
    assert d.decision == "needs_input"
    assert d.needs_field == "item_ids"
    assert [o["title"] for o in d.options] == ["Dune", "Project Hail Mary", "Circe"]


def test_h3_named_item_is_quoted_alone(backend, policy, today):
    d = ev(backend, policy, today, "BK-1002", "changed_mind", ["BK-1002-3"])
    assert d.decision == "return_for_refund"
    assert d.amount == 14.00


def test_unknown_item_asks_again(backend, policy, today):
    d = ev(backend, policy, today, "BK-1002", "changed_mind", ["BK-9999-1"])
    assert d.decision == "needs_input"
    assert d.reason_code == "unknown_item"


def test_missing_reason_asks_for_reason(backend, policy, today):
    d = ev(backend, policy, today, "BK-1001", None)
    assert d.decision == "needs_input"
    assert d.needs_field == "reason"


def test_h4_downloaded_ebook_is_not_refundable(backend, policy, today):
    d = ev(backend, policy, today, "BK-1005", "changed_mind")
    assert d.decision == "ineligible"
    assert d.reason_code == "ebook_downloaded"


def test_ebook_never_downloaded_within_window_is_refundable(backend, policy, today):
    d = ev(backend, policy, today, "BK-1006", "changed_mind")
    assert d.decision == "refund_no_return"
    assert d.amount == 9.99


def test_h5_over_approval_cap_needs_a_human(backend, policy, today):
    d = ev(backend, policy, today, "BK-1007", "damaged")
    assert d.decision == "needs_human"
    assert d.reason_code == "over_approval_limit"
    assert d.amount == 129.99


@pytest.mark.parametrize("reason", ["changed_mind", "damaged", "wrong_item"])
def test_h6_ninety_day_old_order_is_not_eligible_for_any_reason(backend, policy, today, reason):
    d = ev(backend, policy, today, "BK-1008", reason)
    assert d.decision == "ineligible"


def test_not_delivered_is_not_returnable(backend, policy, today):
    d = ev(backend, policy, today, "BK-1009", "changed_mind")
    assert d.decision == "ineligible"
    assert d.reason_code == "not_delivered"


def test_h13_reason_changes_the_terms(backend, policy, today):
    """Why the read-back matters: 'damaged' pays out with no return, 'changed_mind' needs the book back."""
    assert ev(backend, policy, today, "BK-1010", "changed_mind").decision == "return_for_refund"
    assert ev(backend, policy, today, "BK-1010", "damaged").decision == "refund_no_return"


def test_already_returned_item_is_rejected(backend, policy, today):
    backend.record_return(
        quote_id="Q-1001-1", order_id="BK-1001", item_ids=["BK-1001-1"], reason="damaged",
        resolution="refund_no_return", amount=18.99,
    )
    d = ev(backend, policy, today, "BK-1001", "damaged")
    assert d.decision == "ineligible"
    assert d.reason_code == "already_returned"


def test_change_test_shorter_window_moves_only_window_cases(backend, today):
    """A CX lead edits one value. Only the change-of-mind cases inside the old window move."""
    base, shorter = Policy.load(), Policy.load(overrides={"returns.print_return_window_days": 14})
    tom = lambda p: ev(backend, p, today, "BK-1010", "changed_mind").decision  # noqa: E731  delivered 20 days ago
    assert tom(base) == "return_for_refund"
    assert tom(shorter) == "ineligible"
    # Unchanged: damaged items (separate window), and a change of mind inside 14 days.
    assert ev(backend, shorter, today, "BK-1001", "damaged").decision == "refund_no_return"
    assert ev(backend, shorter, today, "BK-1002", "changed_mind", ["BK-1002-1"]).decision == "return_for_refund"


def test_unknown_policy_override_is_rejected():
    with pytest.raises(KeyError):
        Policy.load(overrides={"returns.window_typo": 14})


def test_engine_is_deterministic(backend, policy, today):
    a = ev(backend, policy, today, "BK-1002", "changed_mind", ["BK-1002-1", "BK-1002-2"]).to_dict()
    b = ev(backend, policy, today, "BK-1002", "changed_mind", ["BK-1002-1", "BK-1002-2"]).to_dict()
    assert a == b
    assert a["amount"] == 29.49
