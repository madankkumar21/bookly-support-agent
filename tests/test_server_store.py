"""The web API with the store on: the shared store reaches every conversation, and the clock can be moved."""

import pytest
from fastapi.testclient import TestClient

import app.server as server
from bookly import config
from bookly.agent import Agent
from bookly.store import Store
from tests.jev_fakes import scripted_jev
from tests.test_agent_loop import ScriptedClient, resp, text, tool

TASTE = {"lasting": 0.95, "likes:literary_fiction": 0.9}


def refund_steps(holder):
    return [
        lambda m: resp(tool("get_order", order_id="BK-1001", email="maya.chen@example.com")),
        lambda m: resp(tool("check_return_eligibility", order_id="BK-1001", item_ids=[], reason="damaged")),
        lambda m: resp(text("You qualify for a full refund. Please confirm on the card.")),
        lambda m: resp(tool("create_return", quote_id=holder["agent"].session.latest_quote_id)),
        lambda m: resp(text("All set.")),
    ]


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORE_ENABLED", True)
    monkeypatch.setattr(server, "_store", Store.new(jev=scripted_jev(lambda s, q: TASTE if "lasting" in q else {}, tmp_path)))

    def factory(store=None):
        holder = {}
        holder["agent"] = Agent(client=ScriptedClient(refund_steps(holder)), store=store)
        return holder["agent"]

    monkeypatch.setattr(server, "agent_factory", factory)
    return TestClient(server.app, base_url="http://localhost")


def test_flags_off_api_has_no_store(monkeypatch):
    monkeypatch.setattr(server, "agent_factory", lambda: Agent(client=ScriptedClient([lambda m: resp(text("Hi."))])))
    c = TestClient(server.app, base_url="http://localhost")
    session = c.post("/api/session").json()
    assert set(session) == {"session_id", "model"}
    assert "store" not in c.post("/api/chat", json={"session_id": session["session_id"], "text": "hi"}).json()
    assert c.post("/api/tick", json={"days": 1}).status_code == 404
    assert c.post("/api/store/reset").status_code == 404


def test_store_on_a_refund_opens_a_follow_up_that_a_tick_sends_and_a_new_conversation_sees(client):
    first = client.post("/api/session").json()
    assert first["store"] == {"today": "2026-10-10", "memory": {}, "follow_ups": [], "outbox": [], "contacts": {}}
    sid = first["session_id"]
    one = client.post("/api/chat", json={"session_id": sid, "text": "damaged, BK-1001, maya.chen@example.com. I love literary fiction"}).json()
    two = client.post("/api/chat", json={"session_id": sid, "button": "confirm", "quote_id": one["card"]["quote_id"]}).json()
    assert two["store"]["follow_ups"][0]["status"] == "scheduled"
    assert two["store"]["memory"] == {"maya.chen@example.com": {"likes": ["literary_fiction"], "dislikes": []}}
    jev_rows = [e for e in one["events"] if e["kind"] == "jev"]
    assert jev_rows and jev_rows[0]["purpose"] == "remember" and "saved likes" in jev_rows[0]["decision"]
    assert any(e["kind"] == "follow_up" and e["to_status"] == "scheduled" for e in two["events"])
    assert "I love literary fiction" not in str(two["store"])  # no raw customer text in the panel data

    ticked = client.post("/api/tick", json={"days": 8}).json()
    assert ticked["events"][0]["event"] == "asked" and ticked["store"]["today"] == "2026-10-18"
    assert ticked["store"]["outbox"][0]["to"] == "maya.chen@example.com"

    again = client.post("/api/session").json()  # a new conversation on the same store
    assert again["session_id"] != sid and again["store"]["follow_ups"][0]["status"] == "awaiting_reply"
    assert len(again["systems"]["returns"]) == 1


def test_tick_is_bounded_and_reset_clears_everything(client):
    assert client.post("/api/tick", json={"days": 0}).status_code == 422
    assert client.post("/api/tick", json={"days": 61}).status_code == 422
    sid = client.post("/api/session").json()["session_id"]
    client.post("/api/tick", json={"days": 2})
    fresh = client.post("/api/store/reset").json()
    assert fresh["store"]["today"] == "2026-10-10"
    assert client.post("/api/chat", json={"session_id": sid, "text": "hi"}).status_code == 404  # old conversations end


def test_the_page_and_the_log_say_when_jev_has_no_key(client, monkeypatch, caplog):
    """Store on, no TypeSafe key: the session says so, and the server logs what will not happen when it starts."""
    assert client.post("/api/session").json()["jev_ready"] is False  # conftest removes the key
    with caplog.at_level("WARNING", logger="bookly.web"):
        server.show_startup_notes()
    assert "Jev is never called" in caplog.text and "router" not in caplog.text  # the router is off here
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts_test")
    assert client.post("/api/session").json()["jev_ready"] is True
    assert config.startup_notes() == []
    monkeypatch.setattr(config, "ROUTER_ENGINE", "jev")
    monkeypatch.setattr(config, "ROUTER_ENABLED", False)
    assert any("has no effect" in n for n in config.startup_notes())


def test_a_staff_reply_with_text_is_stored_on_the_ticket_and_the_one_click_reply_still_works(client):
    store = server.get_store()
    first = store.backend.create_ticket("lost_package", {"identity": "verified"})
    second = store.backend.create_ticket("lost_package", {"identity": "verified"})
    out = client.post("/api/ticket/answer", json={"ticket_id": first.ticket_id, "reply": "  Sorry, a replacement ships today.  "}).json()
    by_id = {t["ticket_id"]: t for t in out["systems"]["tickets"]}
    assert by_id[first.ticket_id]["answered_on"] == "2026-10-10"
    assert by_id[first.ticket_id]["staff_reply"] == "Sorry, a replacement ships today."
    out = client.post("/api/ticket/answer", json={"ticket_id": second.ticket_id}).json()
    by_id = {t["ticket_id"]: t for t in out["systems"]["tickets"]}
    assert by_id[second.ticket_id]["answered_on"] == "2026-10-10" and by_id[second.ticket_id]["staff_reply"] is None
    assert client.post("/api/ticket/answer", json={"ticket_id": "T-9999", "reply": "x"}).status_code == 404
