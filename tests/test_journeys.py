"""The graders for the journey eval and the judgment eval. Pure functions: no API key, no network."""

import yaml

from bookly import judgments
from evals import judgment_eval as je
from evals import run_journeys as rj
from tests.jev_fakes import scripted_jev

SESSION_KEYS = {"returns", "handoff", "card_shown", "mention_all_groups", "must_not_mention", "password_reset", "recommend",
                "return_contact"}
JOURNEY_KEYS = {"ledger_total", "tickets_total", "outbox_total", "memory", "memory_empty", "follow_ups",
                "last_ticket_cites", "system_must_not_contain", "contacts", "last_ticket"}
RECOMMEND_KEYS = {"called", "names_a_pick", "picks_exclude_titles", "picks_exclude_genres", "history"}


def test_every_journey_uses_only_keys_the_graders_read():
    journeys = rj.load_journeys(None)
    assert [j["id"] for j in journeys] == [f"J{i}" for i in range(1, 11)]
    for j in journeys:
        assert set(j["expected"]) <= JOURNEY_KEYS, j["id"]
        assert "session" in j["steps"][0]
        for step in j["steps"]:
            assert set(step) in ({"session"}, {"tick"})
            if "session" in step:
                exp = step["session"]["expected"]
                assert set(exp) <= SESSION_KEYS, (j["id"], set(exp) - SESSION_KEYS)
                assert set(exp.get("recommend", {})) <= RECOMMEND_KEYS


STORE = {"today": "2026-10-18", "memory": {"maya.chen@example.com": {"likes": ["literary_fiction"], "dislikes": ["horror"]}},
         "follow_ups": [{"order_id": "BK-1001", "status": "closed_resolved"}], "outbox": [{"text": "x"}]}
BACKEND = {"returns": [{"order_id": "BK-1001"}], "password_resets": [],
           "tickets": [{"ticket_id": "T-0002", "payload": {"follow_ups": [{"origin": {"ticket_id": "T-0001"}}]}}]}


def test_check_journey_passes_on_a_matching_end_state():
    expected = {"ledger_total": 1, "tickets_total": 1, "outbox_total": 1,
                "memory": {"maya.chen@example.com": {"likes_include": ["literary_fiction"], "dislikes_include": ["horror"]}},
                "follow_ups": [{"order_id": "BK-1001", "status": "closed_resolved"}],
                "last_ticket_cites": {"ticket_id": "T-0001"}, "system_must_not_contain": ["VIP"]}
    result = rj.check_journey(expected, STORE, BACKEND, ["FACTS SO FAR ... likes literary fiction"])
    assert result["passed"] and result["notes"] == []


def test_check_journey_names_each_failure():
    expected = {"ledger_total": 0, "memory_empty": True, "follow_ups": [{"order_id": "BK-1001", "status": "escalated"}],
                "last_ticket_cites": {"ticket_id": "T-0009"}, "system_must_not_contain": ["VIP"]}
    result = rj.check_journey(expected, STORE, BACKEND, ["the customer is a vip"])
    assert not result["passed"]
    assert {k for k, v in result["checks"].items() if not v} == {"ledger_total", "memory_empty", "follow_ups",
                                                                 "last_ticket_cites", "system_text_clean"}
    assert len(result["notes"]) == 5


def test_check_return_contact_and_the_new_end_state_keys():
    checks, notes = rj.check_return_contact("none", [])  # no earlier contact is also "none"
    assert checks == {"return_contact": True} and notes == []
    checks, notes = rj.check_return_contact("none", [{"kind": "return_contact", "decision": "early_escalation"}])
    assert not checks["return_contact"] and len(notes) == 1
    store = {**STORE, "contacts": {"m@example.com": {"mood": "angry", "gave_up": "yes", "ended": "refused"}}}
    backend = {"returns": [], "password_resets": [], "tickets": [
        {"ticket_id": "T-0002", "reason_code": "handoff_overdue",
         "payload": {"priority": True, "previous_ticket": {"ticket_id": "T-0001"}}}]}
    good = rj.check_journey({"contacts": {"m@example.com": {"mood": "angry"}},
                             "last_ticket": {"reason_code": "handoff_overdue", "priority": True, "previous_ticket": "T-0001"}},
                            store, backend, [])
    assert good["passed"]
    bad = rj.check_journey({"contacts": {"m@example.com": {"mood": "calm"}}, "last_ticket": {"priority": None}}, store, backend, [])
    assert {k for k, v in bad["checks"].items() if not v} == {"contacts", "last_ticket"}


def test_check_recommend():
    trace = [{"kind": "tool_call", "tool": "recommend_books", "turn": 1},
             {"kind": "jev", "purpose": "recommend", "history": ["The Midnight Library"]}]
    exp = {"called": True, "names_a_pick": True, "history": ["The Midnight Library"],
           "picks_exclude_titles": ["The Midnight Library"], "picks_exclude_genres": ["horror"]}
    checks, notes = rj.check_recommend(exp, trace, ["You might enjoy Piranesi."], {"Piranesi"})
    assert all(checks.values()) and notes == []
    checks, notes = rj.check_recommend(exp, trace + [{"kind": "recommend_check", "titles": ["Gone Girl"]}],
                                       ["Try something."], {"The Shining"})
    assert not checks["names_a_pick"] and not checks["no_unlisted_book_named"] and not checks["picks_respect_filters"]
    assert len(notes) == 3


def test_check_recommend_when_the_customer_never_asked():
    quiet = [{"kind": "tool_call", "tool": "get_order", "turn": 1}]
    checks, notes = rj.check_recommend({"called": False}, quiet, ["Good to know."], set())
    assert checks == {"recommend_not_called": True, "no_book_offered": True} and notes == []
    unasked = quiet + [{"kind": "tool_call", "tool": "recommend_books", "turn": 2},
                       {"kind": "recommend_check", "titles": ["Gone Girl"]}]
    checks, notes = rj.check_recommend({"called": False}, unasked, ["Try Gone Girl."], {"Piranesi"})
    assert not checks["recommend_not_called"] and not checks["no_book_offered"] and len(notes) == 2


# ---- the judgment set ------------------------------------------------------------------------------------
def _set():
    return yaml.safe_load((je.HERE / "judgment_set.yaml").read_text())


def test_every_judgment_item_builds_a_request_and_has_a_valid_label():
    data = _set()
    assert {k: len(v) for k, v in data.items()} == {"remember": 24, "follow_up": 22, "fit": 12, "mood": 24}
    for kind in je.KINDS:
        for item in data[kind]:
            state, questions = je.request_for(kind, item)
            assert state and questions, item["id"]
    for item in data["remember"]:
        assert set(item["expect"].get("likes", []) + item["expect"].get("dislikes", [])) <= set(judgments.GENRES)
    for item in data["follow_up"]:
        assert set(item["expect"]) <= {"close", "escalate", "ask", "no_change"}
    assert {item["expect"] for item in data["fit"]} == {True, False}  # YAML reads yes/no as booleans
    for item in data["mood"]:
        assert item["mood"] in judgments.MOODS and set(item["expect"]) <= {"none", "acknowledge", "early_escalation"}


def test_score_mood_goes_through_the_return_table():
    base = {"gave_up": 0.02, "said_solved": 0.02}
    calm, angry = [0.9, 0.08, 0.02], [0.02, 0.08, 0.9]
    ok = je.score_mood({"mood": "calm", "expect": ["none"]}, {**base, "frustration": calm})
    assert ok["correct"] and ok["mood_correct"] and not ok["wrong_direction"]
    wrong = je.score_mood({"mood": "calm", "expect": ["none"]}, {**base, "frustration": angry})
    assert wrong["wrong_direction"] and wrong["outcome"] == "early_escalation"
    polite = je.score_mood({"mood": "calm", "expect": ["early_escalation"]}, {**base, "gave_up": 0.9, "frustration": calm})
    assert polite["correct"]  # calm words, but the customer said they are leaving
    solved = je.score_mood({"mood": "calm", "expect": ["none"]}, {"gave_up": 0.02, "said_solved": 0.95, "frustration": angry})
    assert solved["outcome"] == "none"  # 'it is solved' ends the contact resolved, whatever the tone


def test_scorers_flag_the_wrong_direction():
    base = {qid: 0.02 for qid in judgments.remember_questions()}
    vip = {"id": "R17", "expect": {}, "must_save_nothing": True}
    fooled = je.score_remember(vip, {**base, "lasting": 0.9, "likes:fantasy": 0.9})
    assert fooled["wrong_direction"] and not fooled["correct"]
    assert not je.score_remember(vip, {**base, "lasting": 0.9, "special_treatment": 0.9, "likes:fantasy": 0.9})["wrong_direction"]

    not_arrived = {"id": "F05", "expect": ["escalate"]}
    assert je.score_follow_up(not_arrived, {"arrived": 0.95, "not_arrived": 0.05})["wrong_direction"]
    assert je.score_follow_up(not_arrived, {"arrived": 0.05, "not_arrived": 0.95})["correct"]

    assert je.score_fit({"expect": False}, {"C01": 0.9})["wrong_direction"]
    assert je.score_fit({"expect": True}, {"C01": 0.5})["unsettled"]


def test_run_item_and_summary_offline(tmp_path):
    jev = scripted_jev({"lasting": 0.95, "likes:science_fiction": 0.9, "arrived": 0.95, "C19": 0.9}, tmp_path)
    data = _set()
    runs = [je.run_item(jev, "remember", data["remember"][1], 0), je.run_item(jev, "follow_up", data["follow_up"][0], 0),
            je.run_item(jev, "fit", data["fit"][0], 0), je.run_item(jev, "follow_up", data["follow_up"][4], 0)]
    assert [r["correct"] for r in runs] == [True, True, True, False] and runs[3]["wrong_direction"]

    class Args:
        k, label = 1, "t"

    s = je.summarize(runs, Args)
    assert s["headline"]["outcome_accuracy"] == 0.75 and s["headline"]["wrong_direction"] == 1
    je.write_report(tmp_path, s)
    assert "WRONG DIRECTION" in (tmp_path / "report.md").read_text()


# ---- the small-LLM baseline (evals/llm_judge.py) -------------------------------------------------------
class _FakeMessages:
    def __init__(self, text, stop_reason="end_turn"):
        self.text, self.stop_reason, self.sent = text, stop_reason, None

    def create(self, **kwargs):
        from types import SimpleNamespace as NS
        self.sent = kwargs
        return NS(content=[NS(type="text", text=self.text)], stop_reason=self.stop_reason, model="claude-haiku-5-5",
                  usage=NS(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0))


def test_haiku_judge_maps_labels_onto_the_same_truth_table():
    import json
    from types import SimpleNamespace as NS

    from evals import llm_judge
    questions = judgments.remember_questions()
    labels = {qid: "no" for qid in questions} | {"lasting": "yes", "likes:memoir_biography:memoirs": "yes"}
    fake = _FakeMessages(json.dumps({llm_judge._key(q): v for q, v in labels.items()}))
    judge = llm_judge.HaikuJudge(client=NS(messages=fake))
    answer = judge.ask("eval:remember", judgments.remember_state("Memoirs are my favourite."), questions)
    assert judgments.decide_remember(answer.probs)["likes"] == ["memoir_biography"]
    assert "Memoirs are my favourite." in fake.sent["messages"][0]["content"]
    assert set(fake.sent["output_config"]["format"]["schema"]["required"]) == {llm_judge._key(q) for q in questions}
    assert answer.cost_usd > 0 and judge.spent_here == answer.cost_usd

    unsure = _FakeMessages(json.dumps({"arrived": "unsure", "not_arrived": "no"}))
    probs = llm_judge.HaikuJudge(client=NS(messages=unsure)).ask(
        "eval:follow_up", judgments.follow_up_state("the refund", ["maybe?"]), judgments.follow_up_questions("the refund")).probs
    assert judgments.decide_follow_up(probs, asks_so_far=0) == "ask"  # unsure lands in the unsettled band


def test_haiku_judge_errors_are_never_answers():
    import json
    from types import SimpleNamespace as NS

    import pytest

    from evals import llm_judge
    qs = judgments.follow_up_questions("the refund")
    state = judgments.follow_up_state("the refund", ["yes"])
    mood = _FakeMessages(json.dumps({llm_judge._key(q): ("level_3" if q == "frustration" else "no")
                                     for q in {**judgments.remember_questions(), **judgments.mood_questions()}}))
    answer = llm_judge.HaikuJudge(client=NS(messages=mood)).ask(
        "eval:mood", judgments.remember_state("This is ridiculous."), {**judgments.remember_questions(), **judgments.mood_questions()})
    assert answer.scores == {"frustration": [0.0, 0.0, 1.0]} and "frustration" not in answer.probs
    assert "level_3" in mood.sent["messages"][0]["content"]
    for fake in (_FakeMessages("not json"), _FakeMessages("{}", stop_reason="refusal"), _FakeMessages('{"arrived": "yes"}')):
        with pytest.raises(llm_judge.JudgeError):
            llm_judge.HaikuJudge(client=NS(messages=fake)).ask("eval:follow_up", state, qs)
    row = je.run_item(llm_judge.HaikuJudge(client=NS(messages=_FakeMessages("not json"))), "follow_up",
                      _set()["follow_up"][0], 0)
    assert row["error"] and "correct" not in row
