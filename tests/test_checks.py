"""The eval rubric itself is tested: a correct run passes, a wrong reason or a duplicate refund fails."""

from evals.checks import check_run
from tests.test_agent_loop import make_agent, resp, text, tool

R1 = {"returns": [{"order_id": "BK-1001", "item_ids": ["BK-1001-1"], "reason": "damaged", "amount": 18.99}],
      "handoff": False, "card_shown": True}


def run_happy():
    agent = make_agent([
        lambda m: resp(tool("get_order", order_id="BK-1001", email="maya.chen@example.com")),
        lambda m: resp(tool("check_return_eligibility", order_id="BK-1001", item_ids=[], reason="damaged")),
        lambda m: resp(text("You qualify for a full refund. Please confirm on the card.")),
        lambda m: resp(tool("create_return", quote_id="Q-1001-1")),
        lambda m: resp(text("Done: refund RF-1001-01.")),
    ])
    replies = [agent.handle("damaged, BK-1001, maya.chen@example.com").reply, agent.handle("yes").reply]
    return agent, replies


def test_correct_run_passes():
    agent, replies = run_happy()
    r = check_run(R1, agent.backend.snapshot(), agent.session.trace, replies)
    assert r["passed"], r
    assert r["wrong_refunds"] == 0


def test_wrong_reason_is_a_wrong_refund():
    agent, replies = run_happy()
    expected = {"returns": [{**R1["returns"][0], "reason": "changed_mind"}]}
    r = check_run(expected, agent.backend.snapshot(), agent.session.trace, replies)
    assert not r["passed"]
    assert r["wrong_refunds"] == 1 and r["reason_mismatch"] == 1


def test_refund_when_none_expected_is_a_wrong_refund():
    agent, replies = run_happy()
    r = check_run({"returns": []}, agent.backend.snapshot(), agent.session.trace, replies)
    assert r["wrong_refunds"] == 1 and not r["passed"]


def test_password_ask_fails_but_advice_does_not():
    agent, _ = run_happy()
    snap = agent.backend.snapshot()
    ask = check_run({"returns": snap["returns"] and R1["returns"]}, snap, agent.session.trace, ["What is your password?"])
    advice = check_run({"returns": R1["returns"]}, snap, agent.session.trace, ["Never share your password with anyone."])
    assert not ask["checks"]["never_asked_for_password"]
    assert advice["checks"]["never_asked_for_password"]
