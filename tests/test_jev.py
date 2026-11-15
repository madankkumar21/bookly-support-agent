"""The Jev wrapper, the truth tables in judgments.py, and the Jev router. No test calls the real API."""

import json

import pytest
from tests.jev_fakes import scripted_jev

from bookly import judgments as j
from bookly.jev import Jev, JevBudgetExceeded, JevError, spent_usd
from bookly.jev_router import JevRouter
from bookly.router import PROCEDURE_INTENTS


# ---- the wrapper ---------------------------------------------------------------------------------------
def test_ask_returns_probabilities_and_logs_the_exact_payload(tmp_path):
    jev = scripted_jev({"arrived": 0.93}, tmp_path, tokens=1000)
    a = jev.ask("follow_up", {"customer_messages": ["it came"]}, j.follow_up_questions("the refund"))
    assert a.probs == {"arrived": 0.93, "not_arrived": 0.05}
    assert a.cost_usd == pytest.approx(1000 * 0.042 / 1_000_000) == jev.spent_here
    row = json.loads((tmp_path / "jev_calls.jsonl").read_text().splitlines()[0])
    assert row["purpose"] == "follow_up" and row["error"] is None
    assert row["request"]["state"] == {"customer_messages": ["it came"]}
    assert row["request"]["questions"]["arrived"]["type"] == "noul"  # the wording is in the log, so it can be rerun
    assert row["answers"]["arrived"] == 0.93


def test_a_failed_call_is_an_error_never_an_answer(tmp_path):
    jev = scripted_jev(tmp_path=tmp_path, fail=TimeoutError("slow"))
    with pytest.raises(JevError):
        jev.ask("router", {}, j.ROUTER_QUESTIONS)
    row = json.loads((tmp_path / "jev_calls.jsonl").read_text().splitlines()[0])
    assert "TimeoutError" in row["error"] and "answers" not in row
    assert spent_usd(tmp_path / "jev_calls.jsonl") == 0.0


def test_calls_stop_at_the_budget_across_instances(tmp_path):
    log = tmp_path / "jev_calls.jsonl"
    first = scripted_jev({}, tmp_path, tokens=1_000_000, budget_usd=0.05)  # one call costs $0.042
    first.ask("router", {}, j.ROUTER_QUESTIONS)
    first.ask("router", {}, j.ROUTER_QUESTIONS)  # $0.084 spent: over the budget now
    with pytest.raises(JevBudgetExceeded):
        first.ask("router", {}, j.ROUTER_QUESTIONS)
    again = Jev(client=first.client_for_tests, log_path=log, budget_usd=0.05)  # a new process reads the same log
    with pytest.raises(JevBudgetExceeded):
        again.ask("router", {}, j.ROUTER_QUESTIONS)
    assert len(first.client_for_tests.calls) == 2


def test_no_key_is_an_error(tmp_path):
    with pytest.raises(JevError):
        Jev(log_path=tmp_path / "x.jsonl").ask("router", {}, j.ROUTER_QUESTIONS)


# ---- bands ---------------------------------------------------------------------------------------------
def test_bands():
    assert [j.band(p) for p in (0.7, 0.69, 0.31, 0.3)] == ["yes", "unsettled", "unsettled", "no"]
    assert j.band(0.8, yes=j.CLOSE_YES) == "unsettled"


# ---- router --------------------------------------------------------------------------------------------
def test_route_keeps_every_intent_and_measures_the_least_certain_procedure():
    intents, conf = j.decide_route({"order_status": 0.1, "returns": 0.95, "policy_rules": 0.02, "account_help": 0.01, "other": 0.9})
    assert intents == ["returns", "other"] and conf == 0.9


def test_either_policy_question_is_enough_for_the_policy_procedure():
    base = {"order_status": 0.02, "returns": 0.97, "other": 0.03}
    assert j.decide_route({**base, "policy_rules": 0.9, "account_help": 0.02})[0] == ["returns", "policy"]
    assert j.decide_route({**base, "policy_rules": 0.02, "account_help": 0.9})[0] == ["returns", "policy"]
    intents, conf = j.decide_route({**base, "policy_rules": 0.1, "account_help": 0.45})  # one part unsettled
    assert intents == ["returns"] and conf == 0.55  # so the policy answer is unsettled, and the router falls back


def test_route_with_no_intent_is_other():
    assert j.decide_route({"order_status": 0.1, "returns": 0.2, "policy_rules": 0.3, "account_help": 0.1, "other": 0.4})[0] == ["other"]


def test_jev_router_falls_back_when_a_procedure_answer_is_unsettled(tmp_path):
    router = JevRouter(scripted_jev({"returns": 0.6, "order_status": 0.02, "policy_rules": 0.03}, tmp_path))
    route = router.classify("my order is messed up")
    assert route.intents == ["returns"] and route.probs["returns"] == 0.6
    assert route.to_load(router.threshold) == (set(PROCEDURE_INTENTS), True)


def test_jev_router_narrows_when_every_procedure_answer_is_settled(tmp_path):
    router = JevRouter(scripted_jev({"returns": 0.97, "other": 0.9}, tmp_path))
    route = router.classify("return a damaged book, and recommend something similar")
    assert route.to_load(router.threshold) == ({"returns", "other"}, False)
    assert route.usage.input_tokens == 200 and route.model


def test_jev_router_error_loads_every_procedure(tmp_path):
    route = JevRouter(scripted_jev(tmp_path=tmp_path, fail=ConnectionError("down"))).classify("hi")
    assert route.error and route.to_load(0.7) == (set(PROCEDURE_INTENTS), True)


def test_router_state_names_both_parts():
    assert set(j.router_state("yes", "Shall I look it up?")) == {"agent_previous_reply", "latest_customer_message"}


# ---- remember ------------------------------------------------------------------------------------------
def _remember(**p):
    base = {qid: 0.02 for qid in j.remember_questions()}
    return j.decide_remember({**base, **{k.replace("__", ":"): v for k, v in p.items()}})


def test_remember_saves_only_genre_keys():
    out = _remember(lasting=0.95, likes__literary_fiction=0.9, dislikes__horror=0.88)
    assert out["likes"] == ["literary_fiction"] and out["dislikes"] == ["horror"]


def test_remember_saves_nothing_when_special_treatment_is_not_a_clear_no():
    for veto in (0.9, 0.5):
        out = _remember(lasting=0.95, special_treatment=veto, likes__fantasy=0.99)
        assert out["likes"] == [] and "special treatment" in out["reason"]


def test_remember_saves_nothing_without_a_lasting_taste():
    for lasting in (0.1, 0.6):
        assert _remember(lasting=lasting, likes__fantasy=0.99)["likes"] == []


def test_a_two_term_genre_is_liked_when_either_term_is():
    """'Memoirs are my favourite' says nothing about biographies. One question per term; code joins them."""
    assert len(j.remember_questions()) == 26  # 2 + 2 x (8 one-term genres + 2 two-term genres x 2 terms)
    assert j.taste_ids("likes", "fantasy") == ["likes:fantasy"]
    assert j.taste_ids("likes", "memoir_biography") == ["likes:memoir_biography:memoirs", "likes:memoir_biography:biographies"]
    out = _remember(lasting=0.95, likes__memoir_biography__memoirs=0.95, dislikes__mystery_thriller__mysteries=0.9)
    assert out["likes"] == ["memoir_biography"] and out["dislikes"] == ["mystery_thriller"]
    mixed = _remember(lasting=0.95, likes__mystery_thriller__thrillers=0.9, dislikes__mystery_thriller__mysteries=0.9)
    assert mixed["likes"] == [] and mixed["dislikes"] == []  # likes one term, dislikes the other: nothing saved
    unsure = _remember(lasting=0.95, likes__memoir_biography__memoirs=0.5)
    assert unsure["likes"] == []


def test_remember_drops_a_genre_that_is_both_liked_and_disliked_or_unsettled():
    out = _remember(lasting=0.9, likes__fantasy=0.9, dislikes__fantasy=0.8, likes__romance=0.6)
    assert out["likes"] == [] and out["dislikes"] == []


# ---- recommend -----------------------------------------------------------------------------------------
BOOKS = [{"book_id": f"B{i}", "title": f"T{i}", "author": "A", "genres": [g], "about": "x"}
         for i, g in enumerate(["fantasy", "romance", "fantasy", "horror", "romance"])]


def test_recommend_tiers_and_order():
    probs = {"B0": 0.75, "B1": 0.9, "B2": 0.5, "B3": 0.5, "B4": 0.1}
    picks = j.decide_recommend(BOOKS, probs, stated={"fantasy"}, limit=5)
    assert [(p["book"]["book_id"], p["tier"]) for p in picks] == [("B0", "A"), ("B1", "B"), ("B2", "C")]


def test_recommend_without_history_ranks_by_stated_genre_only():
    picks = j.decide_recommend(BOOKS, None, stated={"romance"})
    assert [p["book"]["book_id"] for p in picks] == ["B1", "B4"] and all(p["p"] is None for p in picks)
    assert j.decide_recommend(BOOKS, None, stated=set()) == []


def test_recommend_limit():
    assert len(j.decide_recommend(BOOKS, {b["book_id"]: 0.9 for b in BOOKS}, stated=set())) == 3


def test_fit_question_carries_its_own_book():
    q = j.fit_questions(BOOKS[:1])["B0"]
    assert q.instructions["book"]["title"] == "T0" and q.instructions["book"]["genres"] == ["fantasy"]


# ---- follow-up -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("a,n,want", [
    (0.9, 0.1, "close"), (0.9, 0.5, "ask"), (0.9, 0.9, "escalate"),
    (0.8, 0.1, "ask"), (0.5, 0.5, "ask"), (0.5, 0.9, "escalate"),
    (0.1, 0.1, "no_change"), (0.1, 0.5, "ask"), (0.1, 0.9, "escalate"),
])
def test_follow_up_table_has_an_outcome_for_every_cell(a, n, want):
    assert j.decide_follow_up({"arrived": a, "not_arrived": n}, asks_so_far=0) == want


def test_a_second_ask_escalates():
    assert j.decide_follow_up({"arrived": 0.5, "not_arrived": 0.5}, asks_so_far=1) == "escalate"
    assert j.decide_follow_up({"arrived": 0.95, "not_arrived": 0.05}, asks_so_far=1) == "close"


def test_button_texts_are_decided_by_code():
    assert j.decide_follow_up_button(j.FOLLOW_UP_YES) == "close"
    assert j.decide_follow_up_button("no, not yet") == "escalate"
    assert j.decide_follow_up_button("yes") is None
