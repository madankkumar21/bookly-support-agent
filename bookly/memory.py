"""Customer memory: what a verified customer said they like to read, kept across conversations.

What is stored: genre keys from judgments.GENRES, per email. Never the customer's words. The FACTS SO FAR
block is rendered from those keys, so nothing a customer typed in one conversation is replayed as system
text in the next. The raw message is kept in the store's audit list for a person to review, and is never
shown to a model again.

Who decides: Jev judges each message (judgments.remember_questions). Code applies the truth table
(judgments.decide_remember) and writes. The conversational model never writes memory.

What is not here: purchases, returns and tickets. Those are facts the backend already holds; code reads them
from there, for the orders verified in the current conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from bookly import contact, judgments
from bookly.jev import JevError


@dataclass
class CustomerMemory:
    likes: dict[str, str] = field(default_factory=dict)  # genre key -> date it was saved
    dislikes: dict[str, str] = field(default_factory=dict)


class Memory:
    def __init__(self) -> None:
        self.by_email: dict[str, CustomerMemory] = {}

    def get(self, email: str | None) -> CustomerMemory | None:
        return self.by_email.get(email) if email else None

    def save(self, email: str, likes: list[str], dislikes: list[str], today: date) -> None:
        """The newest statement wins: a genre moves from likes to dislikes if the customer now says so."""
        if not likes and not dislikes:
            return
        m = self.by_email.setdefault(email, CustomerMemory())
        for g in likes:
            if g in judgments.GENRES:
                m.dislikes.pop(g, None)
                m.likes.setdefault(g, today.isoformat())
        for g in dislikes:
            if g in judgments.GENRES:
                m.likes.pop(g, None)
                m.dislikes.setdefault(g, today.isoformat())

    def tastes(self, email: str | None) -> dict | None:
        """Genre names for the conversational model, or None when nothing is on file."""
        m = self.get(email)
        if not m or not (m.likes or m.dislikes):
            return None
        return {"likes": [judgments.GENRES[g] for g in m.likes], "dislikes": [judgments.GENRES[g] for g in m.dislikes]}

    def snapshot(self) -> dict:
        return {email: {"likes": sorted(m.likes), "dislikes": sorted(m.dislikes)} for email, m in self.by_email.items()}


def remember(store, session, email: str, text: str) -> None:
    """Judge one customer message and save what the truth table allows. Never raises."""
    try:
        # One request: the mood questions (bookly/contact.py) share this state, so they cost no second call.
        answer = store.jev.ask("remember", judgments.remember_state(text),
                               {**judgments.remember_questions(), **judgments.mood_questions()})
    except JevError as exc:
        session.log("jev", purpose="remember", jev_error=str(exc)[:200], decision="nothing saved: Jev was unavailable")
        return
    decided = judgments.decide_remember(answer.probs)
    store.memory.save(email, decided["likes"], decided["dislikes"], store.backend.today)
    shown = {k: round(v, 2) for k, v in answer.probs.items()
             if k in ("lasting", "special_treatment") or (v > judgments.NO and k not in ("gave_up", "said_solved"))}
    saved = "; ".join(f"{kind} {', '.join(decided[kind])}" for kind in ("likes", "dislikes") if decided[kind])
    session.log("jev", purpose="remember", answers=shown, decision=f"saved {saved}" if saved else decided["reason"],
                latency_ms=answer.latency_ms)
    store.audit.append({"on": store.backend.today.isoformat(), "email": email, "session_id": session.session_id,
                        "text": text, "probs": {k: round(v, 4) for k, v in answer.probs.items()}, "saved": decided})
    contact.read_mood(store, session, email, answer)
