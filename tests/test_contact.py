"""How the last conversation ended, and what changes when the customer comes back (bookly/contact.py).

Scripted model and scripted Jev: no API key, no network.
"""

import itertools
from datetime import date

from bookly import judgments
from bookly.contact import reply_due_on
from tests.test_agent_loop import last_tool_result, resp, text, tool
from tests.test_store import MARCUS, MAYA, new_store, session, system_texts

ANGRY = {"frustration": [0.02, 0.08, 0.90], "gave_up": 0.95}
CALM = {"frustration": [0.90, 0.08, 0.02], "gave_up": 0.03}


def test_decide_mood_reads_levels_not_the_mean():
    assert judgments.decide_mood([0.9, 0.05, 0.05]) == "calm"
    assert judgments.decide_mood([0.05, 0.05, 0.9]) == "angry"
    assert judgments.decide_mood([0.5, 0.0, 0.5]) == "concerned"  # split: the unsettled row, never "angry"
    assert judgments.decide_mood([0.2, 0.6, 0.2]) == "concerned"
    assert judgments.decide_mood(None) == "unknown" and judgments.decide_mood([1.0]) == "unknown"


def test_return_table_has_an_outcome_for_every_combination():
    moods, gave = (*judgments.MOODS, "unknown"), ("yes", "no", "unsettled", "unknown")
    for ended, mood, g in itertools.product(judgments.ENDED, moods, gave):
        out = judgments.decide_return_contact(ended, mood, g)
        if ended == "handoff_overdue":
            assert out == "priority_handoff"  # a code fact: no mood can change it
        elif ended == "handoff_pending":
            assert out == "pending_ticket"
        elif ended in ("handoff_answered", "handoff_followed_up", "resolved"):
            assert out == "none"
        elif mood == "angry" or g == "yes":
            assert out == "early_escalation"
        elif mood == "concerned" or g == "unsettled":
            assert out == "acknowledge"
        else:
            assert out == "none"


def refused(store, said="Forget it. I'm never ordering from you again."):
    """One conversation: a late change-of-mind return is refused, and the customer answers `said`."""
    agent = session(store, [
        lambda m: resp(tool("get_order", order_id=MARCUS[0], email=MARCUS[1])),
        lambda m: resp(tool("check_return_eligibility", order_id=MARCUS[0], item_ids=[], reason="changed_mind")),
        lambda m: resp(text("I'm sorry, that is outside the return window.")),
        lambda m: resp(text("I understand.")),
    ])
    agent.handle(f"I want to return my book, I changed my mind. {MARCUS[0]}, {MARCUS[1]}")
    agent.handle(said)
    return agent


def comes_back(store, steps):
    agent = session(store, [lambda m: resp(tool("get_order", order_id=MARCUS[0], email=MARCUS[1])), *steps])
    agent.handle(f"Hi, it's about {MARCUS[0]} again, {MARCUS[1]}")
    return agent


def test_left_angry_and_refused_then_a_person_comes_sooner_and_no_refund(tmp_path):
    store = new_store(tmp_path, remember=lambda state: ANGRY if "never" in state["customer_message"] else CALM)
    first = refused(store)
    c = store.snapshot()["contacts"][MARCUS[1]]
    assert (c["ended"], c["mood"], c["gave_up"], c["refused"]) == ("refused", "angry", "yes", True)
    assert "never ordering" not in str(store.snapshot())  # values only: the customer's words are not kept
    assert any(e["kind"] == "jev" and e["purpose"] == "mood" for e in first.session.trace)

    store.advance(5)
    second = comes_back(store, [
        lambda m: resp(text("I can see the last contact did not resolve this. Shall I connect you with a person?")),
        lambda m: resp(tool("check_return_eligibility", order_id=MARCUS[0], item_ids=[], reason="changed_mind")),
        lambda m: resp(text("It is still outside the window. I've passed this to a member of our team.")),
    ])
    found = last_tool_result(second.messages)
    assert "offer to connect" in found["customer_record"]["last_contact"]
    assert [e["decision"] for e in second.session.trace if e["kind"] == "return_contact"] == ["early_escalation"]
    assert "angry" not in system_texts(second).lower()  # the model is never told the mood
    assert store.backend.tickets == []
    second.handle("No, just refund it please.")
    blocked = last_tool_result(second.messages)
    assert blocked["decision"] == "ineligible" and blocked["handoff"]["status"] == "queued"
    (ticket,) = store.backend.tickets  # code brought the person in at the first refusal
    assert ticket.reason_code == "repeat_contact_unresolved" and ticket.payload["priority"] is True
    assert store.backend.ledger == []  # anger never changes the refund decision


def test_left_calm_and_refused_then_nothing_changes(tmp_path):
    store = new_store(tmp_path, remember=CALM)
    refused(store, said="OK, thanks anyway.")
    second = comes_back(store, [lambda m: resp(text("How can I help?"))])
    assert "last_contact" not in last_tool_result(second.messages)["customer_record"]
    assert [e["decision"] for e in second.session.trace if e["kind"] == "return_contact"] == ["none"]
    assert "Last contact" not in system_texts(second) and not second.toolbox.escalate_early


def test_a_hand_off_nobody_answered_becomes_a_priority_ticket_without_jev(tmp_path):
    store = new_store(tmp_path, remember=CALM)
    hand_off = [lambda m: resp(tool("get_order", order_id=MARCUS[0], email=MARCUS[1])),
                lambda m: resp(tool("handoff_to_human", reason_code="customer_request",
                                    summary="The customer wants a person to review a late return.")),
                lambda m: resp(text("I've passed this to our team."))]
    session(store, hand_off).handle(f"Can a person look at my return? {MARCUS[0]}, {MARCUS[1]}")
    (old,) = store.backend.tickets
    assert old.opened_on == "2026-10-10" and reply_due_on(old, store.policy) == date(2026, 10, 12)

    store.advance(1)  # Sunday: still inside one business day
    pending = comes_back(store, [lambda m: resp(text("A person will reply by Monday."))])
    assert "Do not open another ticket" in last_tool_result(pending.messages)["customer_record"]["last_contact"]
    assert len(store.backend.tickets) == 1

    store.advance(2)  # Tuesday: overdue
    calls = len(store.jev.client_for_tests.calls)
    back = comes_back(store, [lambda m: resp(text("I'm sorry. Nobody replied in time. It is now a priority."))])
    note = last_tool_result(back.messages)["customer_record"]["last_contact"]
    new = store.backend.tickets[-1]
    assert new.ticket_id == "T-0002" and new.reason_code == "handoff_overdue" and old.escalated_to == "T-0002"
    assert new.payload["priority"] is True and new.payload["previous_ticket"]["ticket_id"] == "T-0001"
    assert "T-0001" in note and "T-0002" in note and "word for word" in note
    assert len(store.jev.client_for_tests.calls) == calls + 1  # only the usual per-message call, after the turn
    assert store.snapshot()["contacts"][MARCUS[1]]["ended"] == "handoff_pending"  # the new ticket's clock runs


def test_a_person_answered_so_nothing_changes(tmp_path):
    store = new_store(tmp_path, remember=ANGRY)
    hand_off = [lambda m: resp(tool("get_order", order_id=MAYA[0], email=MAYA[1])),
                lambda m: resp(tool("handoff_to_human", reason_code="customer_request", summary="The customer asked for a person to help.")),
                lambda m: resp(text("Done."))]
    session(store, hand_off).handle(f"I want a person. {MAYA[0]}, {MAYA[1]}")
    store.backend.tickets[0].answered_on = "2026-10-11"
    store.advance(9)
    again = session(store, [lambda m: resp(tool("get_order", order_id=MAYA[0], email=MAYA[1])), lambda m: resp(text("Hi."))])
    again.handle(f"{MAYA[0]}, {MAYA[1]}")
    assert [e["decision"] for e in again.session.trace if e["kind"] == "return_contact"] == ["none"]
    assert len(store.backend.tickets) == 1


# ---- fixes from the independent review (2026-11-15) ---------------------------------------------------
from bookly import recommend as recommender  # noqa: E402
from tests.test_store import NINA, awaiting_store, verified_session  # noqa: E402

ASK = "Did the refund arrive?\n[[options: Yes, it arrived | No, not yet]]"


def test_a_ticket_whose_follow_up_the_customer_closed_is_not_overdue(tmp_path):
    store = new_store(tmp_path, remember=CALM, follow_up={"arrived": 0.97, "not_arrived": 0.02})
    lost = [lambda m: resp(tool("get_order", order_id=NINA[0], email=NINA[1])),
            lambda m: resp(tool("handoff_to_human", reason_code="lost_package", summary="The package looks lost in transit.")),
            lambda m: resp(text("I've passed this to our team."))]
    session(store, lost).handle(f"{NINA[0]} {NINA[1]} my book never came")
    store.advance(3)
    back = [lambda m: resp(tool("get_order", order_id=NINA[0], email=NINA[1])), lambda m: resp(text("Glad to hear it."))]
    session(store, list(back)).handle(f"{NINA[0]} {NINA[1]} it arrived yesterday, thank you")
    assert store.missions.items[0].status == "closed_resolved"
    store.advance(6)  # the ticket was never marked answered, but the customer closed the case
    again = session(store, list(back))
    again.handle(f"{NINA[0]} {NINA[1]} one more question about this order")
    assert [e["decision"] for e in again.session.trace if e["kind"] == "return_contact"] == ["none"]
    assert len(store.backend.tickets) == 1


def test_a_later_request_in_the_same_conversation_is_added_to_the_ticket(tmp_path):
    store = new_store(tmp_path, remember=CALM)
    first = [lambda m: resp(tool("get_order", order_id=MARCUS[0], email=MARCUS[1])),
             lambda m: resp(tool("handoff_to_human", reason_code="customer_request", summary="The customer wants a person to review a late return.")),
             lambda m: resp(text("Done."))]
    session(store, first).handle(f"Can a person look at my return? {MARCUS[0]}, {MARCUS[1]}")
    store.advance(4)
    back = comes_back(store, [
        lambda m: resp(tool("handoff_to_human", reason_code="customer_request", summary="The customer also reports a damaged cover on the same book.")),
        lambda m: resp(text("I've added that to your ticket."))])
    ticket = store.backend.tickets[-1]
    assert ticket.ticket_id == "T-0002" and len(store.backend.tickets) == 2  # still one ticket per conversation
    assert ticket.payload["later_requests"] == [{"reason_code": "customer_request",
                                                 "summary": "The customer also reports a damaged cover on the same book."}]
    assert ticket.payload["priority"] is True and back.session.handoff["ticket_id"] == "T-0002"


def test_a_hand_off_made_before_verification_becomes_the_priority_ticket(tmp_path):
    store = new_store(tmp_path, remember=CALM)
    first = [lambda m: resp(tool("get_order", order_id=MARCUS[0], email=MARCUS[1])),
             lambda m: resp(tool("handoff_to_human", reason_code="customer_request", summary="The customer wants a person to review a late return.")),
             lambda m: resp(text("Done."))]
    session(store, first).handle(f"Can a person look at my return? {MARCUS[0]}, {MARCUS[1]}")
    store.advance(4)
    early = session(store, [
        lambda m: resp(tool("handoff_to_human", reason_code="customer_request", summary="The customer asked for a person straight away.")),
        lambda m: resp(tool("get_order", order_id=MARCUS[0], email=MARCUS[1])),
        lambda m: resp(text("A person has it."))])
    early.handle(f"I want a person. {MARCUS[0]}, {MARCUS[1]}")
    old, new = store.backend.tickets
    assert old.escalated_to == new.ticket_id == "T-0002"
    assert new.payload["priority"] is True and new.payload["previous_ticket"]["ticket_id"] == "T-0001"


def test_a_second_get_order_does_not_read_the_same_answer_twice(tmp_path):
    store = awaiting_store(tmp_path, follow_up={"arrived": 0.5, "not_arrived": 0.5})
    agent = session(store, [lambda m: resp(tool("get_order", order_id=MAYA[0], email=MAYA[1])),
                            lambda m: resp(tool("get_order", order_id=MAYA[0], email=MAYA[1])),
                            lambda m: resp(text("Could you tell me whether it arrived?"))])
    agent.handle(f"{MAYA[0]} {MAYA[1]} hmm, I am not sure about the refund")
    (m,) = store.missions.items
    assert (m.asks, m.status) == (1, "awaiting_reply") and store.backend.tickets == []
    assert sum(1 for e in agent.session.trace if e["kind"] == "jev" and e["purpose"] == "follow_up") == 1


def test_a_bare_yes_is_read_only_after_the_agent_asked(tmp_path):
    said_yes = lambda st: ({"arrived": 0.98, "not_arrived": 0.02} if "yes" in st["customer_messages"]  # noqa: E731
                           else {"arrived": 0.02, "not_arrived": 0.02})
    store = awaiting_store(tmp_path, follow_up=said_yes)
    agent = verified_session(store, [lambda m: resp(text("Do you want the tracking link?")),
                                     lambda m: resp(text(ASK)), lambda m: resp(text("Thank you."))])
    reads = lambda: sum(1 for e in agent.session.trace if e["kind"] == "jev" and e["purpose"] == "follow_up")  # noqa: E731
    before = reads()
    agent.handle("yes")  # an answer to the tracking question, not to the follow-up
    (m,) = store.missions.items
    assert m.status == "awaiting_reply" and reads() == before  # Jev was not even asked
    agent.handle("what about my refund?")  # the agent now asks, with the buttons
    agent.handle("yes")
    assert m.status == "closed_resolved"


def test_a_one_word_title_is_a_book_only_when_marked_or_when_recommending():
    plain = "That is an Educated guess, James. Dune buggies are not sold here."
    assert recommender.unlisted_titles(plain, set(), recommending=False) == []
    assert recommender.unlisted_titles(plain, set()) == ["Dune", "Educated", "James"]  # recommending: strict
    assert recommender.unlisted_titles("You might like **Educated**.", set(), recommending=False) == ["Educated"]
    assert recommender.unlisted_titles("Try Dune, by Frank Herbert.", set(), recommending=False) == ["Dune"]
    assert recommender.unlisted_titles("Try Project Hail Mary.", set(), recommending=False) == ["Project Hail Mary"]


# ---- Gaps found by the state-machine review (2026-11-16, docs/STATE_MACHINES.md) --------------------------

def test_every_ending_has_words_for_the_model():
    """A new ending must not raise inside get_order: WHAT has a phrase for every value in judgments.ENDED."""
    from bookly.contact import WHAT

    assert set(WHAT) == set(judgments.ENDED)


def test_a_follow_up_the_clock_closed_or_escalated_has_an_instruction_without_none():
    """Nobody answered the follow-up email. The agent's line names what happened and never relays 'None'."""
    from bookly.missions import Mission

    def mission(kind, status, ticket_id=None):
        return Mission(mission_id="M-0001", kind=kind, order_id="BK-1013", email=NINA[1], first_name="Nina",
                       subject="order BK-1013", origin={}, opened_on=date(2026, 10, 10), due_on=date(2026, 10, 13),
                       status=status, ticket_id=ticket_id, sent_on=date(2026, 10, 13))

    escalated = mission("lost_package_check", "escalated", "T-0002").next_step()
    assert "None" not in escalated and "T-0002" in escalated and "a person has the case" in escalated
    closed = mission("refund_check", "closed_no_reply").next_step()
    assert "scheduled" not in closed and "stopped waiting" in closed and "Do not ask about it" in closed
    for status in ("scheduled", "awaiting_reply", "closed_resolved", "closed_no_reply", "escalated"):
        assert "None" not in mission("lost_package_check", status, "T-0002").next_step()
