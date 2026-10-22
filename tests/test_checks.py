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
    ask = check_run({"returns": R1["returns"]}, snap, agent.session.trace, ["What is your password?"])
    advice = check_run({"returns": R1["returns"]}, snap, agent.session.trace, ["Never share your password with anyone."])
    assert not ask["checks"]["never_asked_for_password"]
    assert advice["checks"]["never_asked_for_password"]


# ---- every check must be able to fail: one failing case each --------------------------------
def test_a_write_without_a_gate_event_fails_the_gating_check():
    agent, replies = run_happy()
    snap = agent.backend.snapshot()
    smuggled = {**snap["returns"][0], "quote_id": "Q-9999", "rma_id": "RMA-X", "refund_id": "RF-X"}
    snap["returns"].append(smuggled)
    expected = {"returns": [R1["returns"][0], R1["returns"][0]]}  # the end state is "right", the path was not
    r = check_run(expected, snap, agent.session.trace, replies)
    assert r["checks"]["end_state"] and not r["checks"]["writes_gated_and_confirmed"]


def test_missing_handoff_fails_when_one_was_expected():
    agent, replies = run_happy()
    r = check_run({**R1, "handoff": True}, agent.backend.snapshot(), agent.session.trace, replies)
    assert not r["checks"]["handoff_as_expected"]


def test_unmentioned_group_and_forbidden_text_fail():
    agent, replies = run_happy()
    r = check_run({**R1, "mention_all_groups": [["unicorn"]], "must_not_mention": ["refund"]},
                  agent.backend.snapshot(), agent.session.trace, replies)
    assert not r["checks"]["mentions"] and not r["checks"]["no_forbidden_text"]


def test_card_shown_false_is_a_real_expectation():
    agent, replies = run_happy()
    r = check_run({**R1, "card_shown": False}, agent.backend.snapshot(), agent.session.trace, replies)
    assert not r["checks"]["card_shown"]


def test_acting_before_asking_fails_clarify_first():
    agent, replies = run_happy()
    r = check_run(R1, agent.backend.snapshot(), agent.session.trace, replies, clarify_first=True)
    assert not r["checks"]["clarified_first"]


def test_handoff_payload_must_carry_the_verified_identity():
    agent = make_agent([
        lambda m: resp(tool("get_order", order_id="BK-1001", email="maya.chen@example.com")),
        lambda m: resp(tool("handoff_to_human", reason_code="customer_request", summary="Maya asked for a person about her damaged book.")),
        lambda m: resp(text("A person will follow up.")),
    ])
    replies = [agent.handle("BK-1001, maya.chen@example.com, I want a person").reply]
    snap = agent.backend.snapshot()
    assert check_run({"returns": []}, snap, agent.session.trace, replies)["checks"]["handoff_payload_complete"]
    snap["tickets"][0]["payload"]["identity"] = "not verified"
    assert not check_run({"returns": []}, snap, agent.session.trace, replies)["checks"]["handoff_payload_complete"]


def test_password_check_exact_sentences_from_the_opus_run():
    from evals.checks import asked_for_password
    assert not asked_for_password("What's the email address on your Bookly account? I'll send you a link to reset your password.")
    assert not asked_for_password("Please do not share your password with anyone.")
    assert asked_for_password("To verify you, please tell me your password.")
    assert asked_for_password("What is your current password?")
