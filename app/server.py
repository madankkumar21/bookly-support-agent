"""Web chat for the Bookly agent: one HTML page plus a small JSON API.

    uv run uvicorn app.server:app --port 8000     then open http://localhost:8000

The demo has no login. The session id is the only credential, so it is a 128-bit random token, and
every turn spends the server owner's API key: bind to 127.0.0.1 (uvicorn's default), never 0.0.0.0.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import anthropic

from fastapi import FastAPI, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from bookly import config  # noqa: F401  (loads .env)
from bookly.agent import Agent
from bookly.store import Store

STATIC = Path(__file__).resolve().parent / "static"
MAX_TURNS_PER_SESSION = 40
log = logging.getLogger("bookly.web")

app = FastAPI(title="Bookly support agent")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])  # no DNS-rebinding drive-bys

_sessions: dict[str, Agent] = {}
_locks: dict[str, threading.Lock] = {}
_registry = threading.Lock()
agent_factory = Agent  # tests swap this for a scripted agent
_store: Store | None = None  # BOOKLY_STORE=1 only: one store shared by every conversation on this server


def show_startup_notes() -> None:
    """Settings that run without an error and do less than the developer expects (bookly/config.py)."""
    for note in config.startup_notes():
        log.warning(note)


app.router.on_startup.append(show_startup_notes)  # when the server starts, before the first request


def get_store() -> Store | None:
    """The shared store, created on first use. None with the flag off: then nothing below changes."""
    global _store
    if _store is None and config.STORE_ENABLED:
        with _registry:  # two first requests must not build two stores
            if _store is None:
                _store = Store.new()
    return _store
NO_KEY = "No Anthropic API key found. Copy .env.example to .env, paste your key after ANTHROPIC_API_KEY=, and restart the server."
UNAVAILABLE = "The assistant is unavailable right now. Please try again in a moment."


class TickIn(BaseModel):
    days: int = Field(ge=1, le=60)


class TicketIn(BaseModel):
    ticket_id: str = Field(max_length=16)
    reply: str = Field("", max_length=2000)  # optional text the person wrote; empty keeps the old one-click reply


class ChatIn(BaseModel):
    session_id: str = Field(max_length=64)
    text: str = Field("", max_length=2000)
    button: str | None = None
    quote_id: str | None = Field(None, max_length=32)  # the quote on the card whose button was pressed


def _public_event(e: dict) -> dict:
    """The trace the panel shows: what the agent did and what the code decided."""
    keep = {"turn", "kind", "tool", "input", "is_error", "allowed", "status", "reason", "quote_id", "signal",
            "source", "model", "stop_reason", "latency_ms", "card",
            "skipped", "intents", "confidence", "fallback", "procedures", "route_error",  # route rows
            "purpose", "answers", "decision", "mission_id", "to_status", "jev_error", "titles",
            "ended", "mood", "gave_up",  # store rows
            "order_id", "checks", "request_id", "priority"}  # reship rows (BOOKLY_RESHIP=1)
    out = {k: v for k, v in e.items() if k in keep}
    if e["kind"] == "tool_result":
        out["result"] = e["result"]
    return out


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.post("/api/session")
def new_session() -> dict:
    if agent_factory is Agent and not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(400, NO_KEY)
    store = get_store()
    agent = agent_factory(store=store) if store else agent_factory()
    with _registry:
        _sessions[agent.session.session_id] = agent
        _locks[agent.session.session_id] = threading.Lock()
    out = {"session_id": agent.session.session_id, "model": agent.model}
    if store:  # the page shows the store's panels and controls only when this is present
        out.update(store=store.snapshot(), systems=store.backend.snapshot(), jev_ready=config.jev_key_present())
    return out


@app.post("/api/tick")
def tick(body: TickIn) -> dict:
    """Store on only: move the shared clock forward and run the scheduled follow-up check."""
    store = get_store()
    if store is None:
        raise HTTPException(404, "the store is off; start the server with BOOKLY_STORE=1")
    with store.lock:
        events = store.advance(body.days)
        return {"events": events, "store": store.snapshot(), "systems": store.backend.snapshot()}


@app.post("/api/ticket/answer")
def answer_ticket(body: TicketIn) -> dict:
    """Store on only: a person replied to this ticket (simulated staff). The next visit reads this fact."""
    store = get_store()
    if store is None:
        raise HTTPException(404, "the store is off; start the server with BOOKLY_STORE=1")
    with store.lock:
        ticket = next((t for t in store.backend.tickets if t.ticket_id == body.ticket_id), None)
        if ticket is None:
            raise HTTPException(404, "unknown ticket")
        ticket.answered_on = ticket.answered_on or store.backend.today.isoformat()
        if body.reply.strip() and not ticket.staff_reply:
            ticket.staff_reply = body.reply.strip()
    return {"store": store.snapshot(), "systems": store.backend.snapshot()}


@app.post("/api/store/reset")
def reset_store() -> dict:
    """Store on only: start again from a clean store. Every open conversation ends."""
    global _store
    if not config.STORE_ENABLED:
        raise HTTPException(404, "the store is off; start the server with BOOKLY_STORE=1")
    with _registry:
        _sessions.clear()
        _locks.clear()
        _store = Store.new()
    return {"store": _store.snapshot(), "systems": _store.backend.snapshot()}


# ---- the order console (BOOKLY_RESHIP=1 only) ---------------------------------------------------------
# A deliberately old-style staff page, simulated for the demo (docs/CU_JOURNEY.md). Its one write, Reship, is
# accepted only for an order that has a pending reship_request, which only code writes (bookly/reship.py).

class ReshipIn(BaseModel):
    order_id: str = Field(max_length=16)
    reason_code: str = Field(max_length=32)


def _console_store() -> Store:
    store = get_store()
    if store is None or not config.RESHIP_ENABLED:
        raise HTTPException(404, "the order console is off; start the server with BOOKLY_STORE=1 BOOKLY_RESHIP=1")
    return store


@app.get("/admin")
def admin_page() -> FileResponse:
    _console_store()
    return FileResponse(STATIC / "admin.html")


@app.get("/admin/api/queue")
def admin_queue() -> dict:
    store = _console_store()
    with store.lock:
        return {"today": store.backend.today.isoformat(),
                "requests": [{"request_id": r.request_id, "order_id": r.order_id, "reason_code": r.reason_code,
                              "requested_on": r.requested_on, "priority": r.priority, "status": r.status}
                             for r in store.backend.reship_requests]}


@app.get("/admin/api/order/{order_id}")
def admin_order(order_id: str) -> dict:
    from bookly.backend import normalize_order_id

    store = _console_store()
    with store.lock:
        b = store.backend
        o = b.orders.get(normalize_order_id(order_id) or "")
        if o is None:
            raise HTTPException(404, "ORDER NOT FOUND")
        return {"order_id": o.order_id, "customer_name": o.customer_name, "email": o.email, "status": o.status,
                "placed_at": o.placed_at.isoformat(), "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
                "carrier": o.carrier, "tracking_number": o.tracking_number, "eta": o.eta.isoformat() if o.eta else None,
                "last_scan_at": o.last_scan_at.isoformat() if o.last_scan_at else None, "total": b.order_total(o.order_id),
                "items": [{"item_id": i.item_id, "title": i.title, "format": i.format, "price": i.price} for i in o.items],
                "history": [{"kind": type(r).__name__, **{k: v for k, v in vars(r).items() if k != "cites"}}
                            for r in b.reship_history(o.order_id)]}


@app.post("/admin/api/reship")
def admin_reship(body: ReshipIn) -> dict:
    store = _console_store()
    with store.lock:
        result = store.backend.reship(body.order_id, body.reason_code, store.policy.approval_cap)
    if result["status"] != "reshipped":
        raise HTTPException(409, result)
    return result


@app.post("/api/chat")
def chat(body: ChatIn) -> dict:
    agent = _sessions.get(body.session_id)
    if agent is None:
        raise HTTPException(404, "unknown session; start a new one")
    button = body.button if body.button in ("confirm", "cancel") else None
    if button and not body.quote_id:
        raise HTTPException(400, "a card button press must name the quote_id on its card")
    lock = _locks[body.session_id]
    if not lock.acquire(blocking=False):  # one message at a time per conversation: no racing the gate
        raise HTTPException(409, "this conversation is still answering the previous message")
    try:
        if agent.session.turn >= MAX_TURNS_PER_SESSION:
            raise HTTPException(429, "this conversation has reached its length limit; start a new one")
        try:
            if agent.store:  # every conversation shares this store: ticket ids, follow-ups and the clock.
                with agent.store.lock:  # One turn at a time on it, and no clock tick in the middle of a turn.
                    t = agent.handle(body.text, button=button, quote_id=body.quote_id if button else None)
            else:
                t = agent.handle(body.text, button=button, quote_id=body.quote_id if button else None)
        except anthropic.AuthenticationError:
            with _registry:
                _sessions.pop(body.session_id, None)
                _locks.pop(body.session_id, None)
            raise HTTPException(401, NO_KEY) from None
        except anthropic.APIStatusError as exc:  # e.g. no credit left. The agent rolled this turn back, so a retry is safe.
            log.error("Claude API error %s on session %s: %s", exc.status_code, body.session_id, exc.message)
            raise HTTPException(502, UNAVAILABLE) from None
    finally:
        lock.release()
    return {
        "reply": t.reply,
        "options": t.options,
        "card": t.card,
        "handoff": t.handoff,
        "events": [_public_event(e) for e in t.events if e["kind"] not in ("customer", "agent")],
        "latency_ms": t.usage["latency_ms"],
        **({"notes": t.notes} if t.notes else {}),  # grey system notes written by code (BOOKLY_RESHIP=1 only)
        "systems": agent.backend.snapshot(),
        **({"store": agent.store.snapshot()} if agent.store else {}),
    }
