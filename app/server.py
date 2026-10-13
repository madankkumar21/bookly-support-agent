"""Web chat for the Bookly agent: one HTML page plus a small JSON API.

    uv run uvicorn app.server:app --port 8000     then open http://localhost:8000
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import anthropic

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bookly import config  # noqa: F401  (loads .env)
from bookly.agent import Agent

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="Bookly support agent")

_sessions: dict[str, Agent] = {}
_lock = threading.Lock()
agent_factory = Agent  # tests swap this for a scripted agent
NO_KEY = "No Anthropic API key found. Copy .env.example to .env, paste your key after ANTHROPIC_API_KEY=, and restart the server."


class ChatIn(BaseModel):
    session_id: str
    text: str = ""
    button: str | None = None


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
    with _lock:
        _sessions[agent.session.session_id] = agent
    return {"session_id": agent.session.session_id, "model": agent.model}


@app.post("/api/chat")
def chat(body: ChatIn) -> dict:
    agent = _sessions.get(body.session_id)
    if agent is None:
        raise HTTPException(404, "unknown session; start a new one")
    button = body.button if body.button in ("confirm", "cancel") else None
    try:
        t = agent.handle(body.text, button=button)
    except anthropic.AuthenticationError:
        _sessions.pop(body.session_id, None)
        raise HTTPException(401, NO_KEY)
    except anthropic.APIStatusError as exc:  # e.g. no credit left; the conversation cannot continue safely
        _sessions.pop(body.session_id, None)
        raise HTTPException(502, f"The Claude API returned an error ({exc.status_code}): {exc.message}. Refresh to start again.")
    return {
        "reply": t.reply,
        "options": t.options,
        "card": t.card,
        "handoff": t.handoff,
        "events": [_public_event(e) for e in t.events if e["kind"] not in ("customer", "agent")],
        "latency_ms": t.usage["latency_ms"],
        "systems": {
            "returns": [r.__dict__ for r in agent.backend.ledger],
            "tickets": [{"ticket_id": tk.ticket_id, "reason_code": tk.reason_code, "payload": tk.payload} for tk in agent.backend.tickets],
            "password_resets": agent.backend.password_resets,
        },
    }
