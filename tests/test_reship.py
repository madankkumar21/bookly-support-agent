"""The reship journey (BOOKLY_RESHIP=1, docs/CU_JOURNEY.md): delay_watch, the reship gate, and flag-off behaviour.

Scripted model and scripted Jev: no API key, no network.
"""

import pytest
from fastapi.testclient import TestClient

from bookly import config
from bookly.backend import Backend
from tests.test_agent_loop import last_tool_result, resp, text, tool
from tests.test_store import new_store, session

RILEY = ("BK-1020", "riley.morgan@example.com")
ANGRY = {"frustration": [0.02, 0.08, 0.90]}
NOT_ARRIVED = {"arrived": 0.02, "not_arrived": 0.95}


@pytest.fixture
def reship_on(monkeypatch):
    monkeypatch.setattr(config, "STORE_ENABLED", True)
    monkeypatch.setattr(config, "RESHIP_ENABLED", True)


def visit(store, lines, replies=1):
    """One conversation: get_order on the first line, then a plain reply to every line."""
    steps = [lambda m: resp(tool("get_order", order_id=RILEY[0], email=RILEY[1]))]
    steps += [lambda m: resp(text("Okay."))] * len(lines)
    agent = session(store, steps)
    for line in lines:
        agent.handle(line)
    return agent


def journey_store(tmp_path):
    return new_store(tmp_path, remember=ANGRY, follow_up=NOT_ARRIVED)


# ---- delay_watch ----------------------------------------------------------------------------------------
def test_late_package_opens_a_delay_watch_and_a_not_arrived_reply_reopens_it_without_a_ticket(tmp_path, reship_on):
    store = journey_store(tmp_path)
    visit(store, [f"Where is {RILEY[0]}? It was due on the 8th. {RILEY[1]}", "This is ridiculous."])
    [m1] = store.missions.items
    assert m1.kind == "delay_watch" and m1.status == "scheduled" and m1.due_on.isoformat() == "2026-10-12"
    assert store.contacts.by_email[RILEY[1]].mood == "angry"

    store.advance(3)  # 10/13: inside the lost window
    assert m1.status == "awaiting_reply" and "running late" in store.outbox[-1]["text"]
    agent = visit(store, [f"It's still not here and nothing has changed on the tracking. {RILEY[0]}, {RILEY[1]}"])
    assert m1.status == "closed_still_missing"
    m2 = store.missions.items[-1]
    assert m2.kind == "delay_watch" and m2.status == "scheduled" and m2.opened_on.isoformat() == "2026-10-13"
    assert store.backend.tickets == [] and store.backend.reship_requests == []
    record = last_tool_result(agent.messages)["customer_record"]
    assert "not yet treated as lost" in " ".join(record["follow_ups"])
    assert "last_contact" in record  # the early-escalation offer: the last visit ended angry


def test_full_journey_writes_one_priority_request_and_the_console_reships_once(tmp_path, reship_on):
    store = journey_store(tmp_path)
    visit(store, [f"Where is {RILEY[0]}? {RILEY[1]}", "This is ridiculous. I'm done waiting on you people."])
    store.advance(3)
    visit(store, [f"It's still not here. {RILEY[0]}, {RILEY[1]}", "No. I don't want to talk to anyone."])
    store.advance(4)  # 10/17: five business days without a scan, so lost
    agent = visit(store, [f"Still nothing has arrived. {RILEY[0]}, {RILEY[1]}"])
    [req] = store.backend.reship_requests
    assert req.order_id == RILEY[0] and req.status == "pending" and req.priority is True
    assert req.cites == ["2026-10-10", "2026-10-13"]
    assert store.backend.tickets == []  # no lost-package ticket: code took the reship path
    assert agent.toolbox.return_contact["first"] is None  # the person follows up; no second chat offer
    assert "last_contact" not in last_tool_result([m for m in agent.messages if m["role"] == "user"][:2])["customer_record"]

    b = store.backend
    assert b.reship(RILEY[0], "lost_in_transit", store.policy.approval_cap)["status"] == "reshipped"
    facts = agent.toolbox.store_facts()
    assert any("You first told us about this on Saturday, October 10, and again on Tuesday, October 13" in f
               for f in facts)
    assert any("check in with you by email" in f for f in facts)


def two_angry_visits(tmp_path):
    """Visits 1 and 2 of the journey, then the clock to 10/17 (lost). Visit 2 offers a person; no ticket."""
    store = journey_store(tmp_path)
    visit(store, [f"Where is {RILEY[0]}? {RILEY[1]}", "This is ridiculous. I'm done waiting on you people."])
    store.advance(3)
    visit(store, [f"It's still not here. {RILEY[0]}, {RILEY[1]}", "No. I don't want to talk to anyone."])
    store.advance(4)
    return store


HANDOFF = {"header": "BK-1020 · Riley Morgan · Priority follow-up",
           "contacts": ["10/10 — 2 days late", "10/13 — still missing; declined a person",
                        "10/17 — lost (no scan since 10/9)"],
           "done": "Reship RS-1020-01 issued in the order console on 10/17.",
           "next": "Confirm the replacement shipped, then check in with the customer."}
MOOD_WORDS = ("angry", "mood", "frustrat")


def test_a_priority_reship_opens_one_staff_ticket_and_one_chat_note(tmp_path, reship_on):
    store = two_angry_visits(tmp_path)
    b = store.backend
    confirm = lambda m: resp(text(f"Your replacement is on its way (reship {b.reships[0].reship_id})."))  # noqa: E731
    agent = session(store, [lambda m: resp(tool("get_order", order_id=RILEY[0], email=RILEY[1])),
                            lambda m: resp(text("Okay.")), confirm, confirm])
    first = agent.handle(f"Still nothing has arrived. {RILEY[0]}, {RILEY[1]}")
    assert first.notes == [] and b.tickets == []  # requested, not done: nobody is escalated yet

    result = b.reship(RILEY[0], "lost_in_transit", store.policy.approval_cap)
    [rs], [ticket] = b.reships, b.tickets
    assert result["ticket_id"] == rs.ticket_id == ticket.ticket_id
    assert ticket.reason_code == "reship_followup" and ticket.payload["priority"] is True
    assert ticket.payload["reship_id"] == rs.reship_id and ticket.payload["request_id"] == rs.request_id
    assert ticket.payload["earlier_contacts"] == ["2026-10-10", "2026-10-13"]
    assert not any(w in str(ticket.payload).lower() for w in MOOD_WORDS)

    done = agent.handle("Okay. Has it actually been sent?")
    assert done.notes == [{"kind": "handoff", "label": "Handed to staff",
                           "text": f"Priority follow-up · ticket {ticket.ticket_id} · reship {rs.reship_id}"}]
    assert not any(w in str(done.notes).lower() for w in MOOD_WORDS)
    assert agent.handle("Thanks.").notes == []  # shown once
    assert len(b.tickets) == 1
    assert next(m for m in store.missions.items if m.status == "closed_reship_requested").ticket_id == ticket.ticket_id


def test_the_handoff_summary_is_built_from_stored_facts(tmp_path, reship_on):
    store = two_angry_visits(tmp_path)
    b = store.backend
    session(store, [lambda m: resp(tool("get_order", order_id=RILEY[0], email=RILEY[1])),
                    lambda m: resp(text("Okay."))]).handle(f"Still nothing has arrived. {RILEY[0]}, {RILEY[1]}")
    [req] = b.reship_requests  # the per-visit facts are on the request code wrote, before any reship
    assert req.contacts == [{"on": "2026-10-10", "fact": "2 days late"},
                            {"on": "2026-10-13", "fact": "still missing; declined a person"},
                            {"on": "2026-10-17", "fact": "lost (no scan since 10/9)"}]
    offered = [h for m in store.missions.items for h in m.history if h["event"] == "person_offered"]
    assert [h["on"] for h in offered] == ["2026-10-13"]  # the store fact behind "declined a person"
    b.reship(RILEY[0], "lost_in_transit", store.policy.approval_cap)
    [ticket] = b.tickets
    assert ticket.payload["handoff"] == HANDOFF
    assert not any(w in str(ticket.payload["handoff"]).lower() for w in MOOD_WORDS)
    assert "jev" not in str(ticket.payload).lower() and "score" not in str(ticket.payload).lower()


def test_a_visit_that_opened_a_ticket_is_not_called_declined(tmp_path, reship_on):
    store = two_angry_visits(tmp_path)
    prior = store.contacts.by_email[RILEY[1]]
    prior.ticket_id = "T-9999"  # visit 2 brought a person in: the fact must not say "declined"
    from bookly import reship as reships

    facts = reships.contact_facts(store, store.backend.orders[RILEY[0]], prior)
    assert facts[1] == {"on": "2026-10-13", "fact": "still missing"}


def test_the_api_returns_the_handoff_summary_and_the_handoff_note(tmp_path, reship_on, monkeypatch):
    import app.server as server
    from tests.test_agent_loop import ScriptedClient

    store = two_angry_visits(tmp_path)
    session(store, [lambda m: resp(tool("get_order", order_id=RILEY[0], email=RILEY[1])),
                    lambda m: resp(text("Okay."))]).handle(f"Still nothing has arrived. {RILEY[0]}, {RILEY[1]}")
    steps = [lambda m: resp(tool("get_order", order_id=RILEY[0], email=RILEY[1])),
             lambda m: resp(text("Your replacement is on its way (reship RS-1020-01)."))]
    monkeypatch.setattr(server, "agent_factory", lambda **kw: server.Agent(client=ScriptedClient(steps), **kw))
    server._store = store
    try:
        c = TestClient(server.app, base_url="http://localhost")
        assert c.post("/admin/api/reship", json={"order_id": RILEY[0], "reason_code": "lost_in_transit"}).status_code == 200
        sid = c.post("/api/session").json()["session_id"]
        d = c.post("/api/chat", json={"session_id": sid, "text": f"Has it been sent? {RILEY[0]}, {RILEY[1]}"}).json()
        [ticket] = d["systems"]["tickets"]
        assert ticket["reason_code"] == "reship_followup" and ticket["payload"]["handoff"] == HANDOFF
        assert d["notes"] == [{"kind": "handoff", "label": "Handed to staff",
                               "text": "Priority follow-up · ticket T-0001 · reship RS-1020-01"}]
    finally:
        server._store = None


def test_a_non_priority_reship_opens_no_ticket_and_no_note(tmp_path, reship_on):
    store = journey_store(tmp_path)
    b = store.backend
    b.add_reship_request(RILEY[0], "lost_in_transit", False, ["2026-10-10"])
    result = b.reship(RILEY[0], "lost_in_transit", store.policy.approval_cap)
    assert result == {"status": "reshipped", "reship_id": "RS-1020-01", "priority": False}
    assert b.tickets == [] and b.reships[0].ticket_id is None
    agent = session(store, [lambda m: resp(tool("get_order", order_id=RILEY[0], email=RILEY[1])),
                            lambda m: resp(text("Your replacement is on its way (reship RS-1020-01)."))])
    assert agent.handle(f"Has it been sent? {RILEY[0]}, {RILEY[1]}").notes == []


def test_the_chat_agent_has_no_reship_tool(reship_on, tmp_path):
    agent = session(journey_store(tmp_path), [])
    assert not any("reship" in t["name"] for t in agent.tools)


def test_a_model_lost_package_handoff_is_not_needed_once_code_requested_a_reship(tmp_path, reship_on):
    store = journey_store(tmp_path)
    visit(store, [f"Where is {RILEY[0]}? {RILEY[1]}"])
    store.advance(7)
    agent = session(store, [lambda m: resp(tool("get_order", order_id=RILEY[0], email=RILEY[1])),
                            lambda m: resp(tool("handoff_to_human", reason_code="lost_package", summary="Lost.")),
                            lambda m: resp(text("Okay."))])
    agent.handle(f"Still nothing has arrived. {RILEY[0]}, {RILEY[1]}")
    assert len(store.backend.reship_requests) == 1 and store.backend.tickets == []
    assert last_tool_result(agent.messages)["status"] == "not_needed"


# ---- the console gate -----------------------------------------------------------------------------------
def test_console_rejects_an_order_without_a_pending_request():
    b = Backend.load()
    assert b.reship("BK-1020", "lost_in_transit", 100.0) == {"status": "rejected", "reason": "no_pending_request"}
    assert b.reships == [] and len(b.console_posts) == 1


def test_console_rejects_a_repeat_reship():
    b = Backend.load()
    b.add_reship_request("BK-1020", "lost_in_transit", False, [])
    assert b.reship("BK-1020", "lost_in_transit", 100.0)["status"] == "reshipped"
    assert b.reship("BK-1020", "lost_in_transit", 100.0)["reason"] == "already_reshipped"
    with pytest.raises(ValueError):
        b.add_reship_request("BK-1020", "lost_in_transit", False, [])
    assert len(b.reships) == 1


def test_console_rejects_over_the_value_cap_and_a_wrong_reason():
    b = Backend.load()
    b.add_reship_request("BK-1020", "lost_in_transit", False, [])
    assert b.reship("BK-1020", "lost_in_transit", 10.0)["reason"] == "over_value_cap"
    assert b.reship("BK-1020", "damaged_in_transit", 100.0)["reason"] == "reason_code_mismatch"
    assert b.reships == []


def test_chat_gate_refuses_an_order_over_the_cap(tmp_path, reship_on, monkeypatch):
    store = journey_store(tmp_path)
    monkeypatch.setattr(type(store.policy), "approval_cap", property(lambda self: 5.0))
    visit(store, [f"Where is {RILEY[0]}? {RILEY[1]}"])
    store.advance(7)
    visit(store, [f"Still nothing has arrived. {RILEY[0]}, {RILEY[1]}"])
    assert store.backend.reship_requests == []
    assert [t.reason_code for t in store.backend.tickets] == ["lost_package"]  # the existing path: a person decides


def test_console_endpoint_rejects_without_a_request(reship_on):
    import app.server as server

    server._store = None
    try:
        c = TestClient(server.app, base_url="http://localhost")
        assert c.get("/admin").status_code == 200
        r = c.post("/admin/api/reship", json={"order_id": "BK-1020", "reason_code": "lost_in_transit"})
        assert r.status_code == 409 and r.json()["detail"]["reason"] == "no_pending_request"
    finally:
        server._store = None


# ---- flag off -------------------------------------------------------------------------------------------
def test_flag_off_opens_no_delay_watch_and_keeps_the_snapshot_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORE_ENABLED", True)
    monkeypatch.setattr(config, "RESHIP_ENABLED", False)
    store = journey_store(tmp_path)
    visit(store, [f"Where is {RILEY[0]}? {RILEY[1]}"])
    assert store.missions.items == []
    assert set(store.backend.snapshot()) == {"returns", "password_resets", "tickets"}
    assert store.backend.tickets == []


def test_flag_off_chat_response_has_no_notes_key(monkeypatch):
    import app.server as server
    from tests.test_agent_loop import ScriptedClient

    monkeypatch.setattr(config, "STORE_ENABLED", False)
    monkeypatch.setattr(config, "RESHIP_ENABLED", False)
    monkeypatch.setattr(server, "agent_factory", lambda **kw: server.Agent(client=ScriptedClient([lambda m: resp(text("Hi."))]), **kw))
    server._store = None
    try:
        c = TestClient(server.app, base_url="http://localhost")
        sid = c.post("/api/session").json()["session_id"]
        d = c.post("/api/chat", json={"session_id": sid, "text": "Hello"}).json()
        assert d["reply"] and "notes" not in d
    finally:
        server._store = None


def test_flag_off_console_is_not_served(monkeypatch):
    import app.server as server

    monkeypatch.setattr(config, "STORE_ENABLED", True)
    monkeypatch.setattr(config, "RESHIP_ENABLED", False)
    server._store = None
    try:
        c = TestClient(server.app, base_url="http://localhost")
        assert c.get("/admin").status_code == 404
        assert c.post("/admin/api/reship", json={"order_id": "BK-1020", "reason_code": "x"}).status_code == 404
    finally:
        server._store = None
