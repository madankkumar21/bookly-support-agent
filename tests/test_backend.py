"""Order lookup and identity: a wrong email and an unknown order look the same (H9)."""

import pytest

from bookly.backend import normalize_order_id


@pytest.mark.parametrize("raw", ["BK-1001", "bk1001", "#1001", "1001", "order BK 1001"])
def test_order_id_forms(raw):
    assert normalize_order_id(raw) == "BK-1001"


def test_lookup_needs_matching_email(backend):
    assert backend.lookup("BK-1001", "Maya.Chen@example.com ").order_id == "BK-1001"


def test_h9_wrong_email_and_unknown_order_are_indistinguishable(backend):
    assert backend.lookup("BK-1001", "someone@else.com") is None
    assert backend.lookup("BK-4040", "maya.chen@example.com") is None


def test_ledger_is_unique_on_quote_id(backend):
    a = backend.record_return(quote_id="Q-1", order_id="BK-1001", item_ids=["BK-1001-1"], reason="damaged",
                              resolution="refund_no_return", amount=18.99)
    b = backend.record_return(quote_id="Q-1", order_id="BK-1001", item_ids=["BK-1001-1"], reason="damaged",
                              resolution="refund_no_return", amount=18.99)
    assert a is b
    assert len(backend.ledger) == 1
