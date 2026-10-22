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

STATIC = Path(__file__).resolve().parent / "static"
MAX_TURNS_PER_SESSION = 40
log = logging.getLogger("bookly.web")

app = FastAPI(title="Bookly support agent")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])  # no DNS-rebinding drive-bys

_sessions: dict[str, Agent] = {}
_locks: dict[str, threading.Lock] = {}
_registry = threading.Lock()
agent_factory = Agent  # tests swap this for a scripted agent
NO_KEY = "No Anthropic API key found. Copy .env.example to .env, paste your key after ANTHROPIC_API_KEY=, and restart the server."
UNAVAILABLE = "The assistant is unavailable right now. Please try again in a moment."


class ChatIn(BaseModel):
    session_id: str = Field(max_length=64)
    text: str = Field("", max_length=2000)
    button: str | None = None
    quote_id: str | None = Field(None, max_length=32)  # the quote on the card whose button was pressed


def _public_event(e: dict) -> dict:
    """The trace the panel shows: what the agent did and what the code decided."""
    keep = {"turn", "kind", "tool", "input", "is_error", "allowed", "status", "reason", "quote_id", "signal",
            "source", "model", "stop_reason", "latency_ms", "card"}
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
    agent = agent_factory()
    with _registry:
        _sessions[agent.session.session_id] = agent
        _locks[agent.session.session_id] = threading.Lock()
    return {"session_id": agent.session.session_id, "model": agent.model}


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
        "systems": agent.backend.snapshot(),
    }
