"""Tool behaviour that is decided in code: the lookup lock, the pinned refusal text, the lost-package rule."""

from bookly import config
from bookly.state import Session
from bookly.tools import Toolbox


def toolbox(backend, policy, policy_text):
    return Toolbox(Session(), backend, policy, policy_text)


def test_lookups_lock_after_repeated_misses_even_with_the_right_email(backend, policy, policy_text):
    tb = toolbox(backend, policy, policy_text)
    for _ in range(config.MAX_LOOKUP_MISSES):
        assert tb._t_get_order("BK-1001", "guess@example.com")["status"] == "no_match"
    assert tb._t_get_order("BK-1001", "maya.chen@example.com")["status"] == "locked"
    assert "BK-1001" not in tb.s.verified_orders


def test_ineligible_explanation_comes_from_pinned_policy_text(backend, policy, policy_text):
    tb = toolbox(backend, policy, policy_text)
    tb.s.verified_orders["BK-1008"] = "Marcus Webb"
    out = tb._t_check_return_eligibility("BK-1008", [], "changed_mind")
    assert out["decision"] == "ineligible"
    assert f"within {policy.print_window} days of delivery" in out["explanation"][0]


def test_tool_results_carry_no_wall_clock(backend, policy, policy_text):
    tb = toolbox(backend, policy, policy_text)
    result, is_error = tb.run("get_order", {"order_id": "BK-1001", "email": "maya.chen@example.com"})
    assert not is_error and "ts" not in result


def test_lost_package_counts_from_the_last_scan_or_the_estimate(backend, policy, policy_text):
    tb = toolbox(backend, policy, policy_text)
    stuck = tb._t_get_order("BK-1013", backend.find_order("BK-1013").email)["order"]
    in_transit = tb._t_get_order("BK-1009", backend.find_order("BK-1009").email)["order"]
    assert stuck["likely_lost"] and not in_transit["likely_lost"]
