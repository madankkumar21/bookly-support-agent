"""The web API, driven by a scripted model: a card appears, the Confirm button creates one refund."""

import pytest
from fastapi.testclient import TestClient

import app.server as server
from tests.test_agent_loop import make_agent, resp, text, tool


def scripted():
    return make_agent([
        lambda m: resp(tool("get_order", order_id="BK-1001", email="maya.chen@example.com")),
        lambda m: resp(tool("check_return_eligibility", order_id="BK-1001", item_ids=[], reason="damaged")),
        lambda m: resp(text("You qualify for a full refund. Please confirm on the card.")),
        lambda m: resp(tool("create_return", quote_id="Q-1001-1")),
        lambda m: resp(text("Done.")),
    ])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "agent_factory", scripted)
    return TestClient(server.app, base_url="http://localhost")  # the app only trusts localhost and 127.0.0.1


def test_chat_flow_with_card_and_confirm_button(client):
    assert client.get("/").status_code == 200
    sid = client.post("/api/session").json()["session_id"]
    assert len(sid) == 32  # 128-bit random token: the session's only credential
    first = client.post("/api/chat", json={"session_id": sid, "text": "damaged, BK-1001, maya.chen@example.com"}).json()
    assert first["card"]["amount"] == "$18.99"
    assert any(e["kind"] == "tool_call" for e in first["events"])
    second = client.post("/api/chat", json={"session_id": sid, "button": "confirm", "quote_id": first["card"]["quote_id"]}).json()
    assert len(second["systems"]["returns"]) == 1
    assert any(e["kind"] == "gate" and e["allowed"] for e in second["events"])


def test_button_press_must_name_its_card(client):
    sid = client.post("/api/session").json()["session_id"]
    r = client.post("/api/chat", json={"session_id": sid, "button": "confirm"})
    assert r.status_code == 400


def test_oversized_message_is_rejected_before_the_model_sees_it(client):
    sid = client.post("/api/session").json()["session_id"]
    r = client.post("/api/chat", json={"session_id": sid, "text": "x" * 2001})
    assert r.status_code == 422


def test_unknown_session_is_404(client):
    assert client.post("/api/chat", json={"session_id": "nope", "text": "hi"}).status_code == 404


def test_other_hosts_are_refused():
    assert TestClient(server.app, base_url="http://evil.example").get("/").status_code == 400


def test_missing_key_gives_a_clear_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(server, "agent_factory", server.Agent)
    r = TestClient(server.app, base_url="http://localhost").post("/api/session")
    assert r.status_code == 400 and "ANTHROPIC_API_KEY" in r.json()["detail"]
