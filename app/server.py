"""Web chat for the Bookly agent: one HTML page plus a small JSON API.

    uv run uvicorn app.server:app --port 8000     then open http://localhost:8000
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bookly.agent import Agent

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="Bookly support agent")

_sessions: dict[str, Agent] = {}
_lock = threading.Lock()
agent_factory = Agent  # tests swap this for a scripted agent


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
    t = agent.handle(body.text, button=button)
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
