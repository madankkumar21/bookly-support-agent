"""What outlives one conversation: the store. Off by default (BOOKLY_STORE=1 turns it on).

Without a store, every conversation has its own backend, and nothing is remembered. With one, every
conversation shares:
- one backend, so a return made in one chat is on file in the next (no second refund of the same book);
- one quote counter, so a quote id is never reused across chats;
- customer memory (bookly/memory.py), follow-ups (bookly/missions.py) and a simulated outbox;
- how each customer's last conversation ended (bookly/contact.py);
- one clock, which advance() moves forward so a follow-up can come due.

Jev, the decision model, keeps no context between calls. This store is where the context lives. Jev judges
the language; the code here and in judgments.py decides what changes.

The store is in memory: it survives a new chat, not a server restart.
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from bookly.backend import Backend
from bookly.contact import Contacts
from bookly.jev import Jev
from bookly.kb import PolicyText
from bookly.memory import Memory
from bookly.missions import Missions
from bookly.policy import Policy


def session_email(session, backend) -> str | None:
    """The one email behind this conversation's verified orders. None before verification, and None if the
    verified orders belong to different emails: then the customer record stays closed."""
    emails = {backend.orders[o].email for o in session.verified_orders}
    return next(iter(emails)) if len(emails) == 1 else None


@dataclass
class Store:
    backend: Backend
    policy: Policy
    kb: PolicyText
    jev: Jev
    memory: Memory = field(default_factory=Memory)
    missions: Missions = field(default_factory=Missions)
    contacts: Contacts = field(default_factory=Contacts)  # how each customer's last conversation ended
    outbox: list[dict] = field(default_factory=list)  # simulated emails Bookly sent
    audit: list[dict] = field(default_factory=list)  # every remember decision, with the raw text, for a person
    quote_seq: Any = field(default_factory=lambda: itertools.count(1), repr=False)
    lock: Any = field(default_factory=threading.RLock, repr=False)

    @classmethod
    def new(cls, jev: Jev | None = None, policy: Policy | None = None, backend: Backend | None = None) -> Store:
        policy = policy or Policy.load()
        return cls(backend=backend or Backend.load(), policy=policy, kb=PolicyText(policy), jev=jev or Jev())

    def advance(self, days: int) -> list[dict]:
        """Move the shared clock forward and run the scheduled check on follow-ups."""
        with self.lock:
            self.backend.today = self.backend.today + timedelta(days=max(0, int(days)))
            return self.missions.run_due(self.backend.today, self.backend, self.kb, self.outbox)

    def snapshot(self) -> dict:
        """End state for the eval checks and the operator panel. No raw customer text."""
        return {
            "today": self.backend.today.isoformat(),
            "memory": self.memory.snapshot(),
            "follow_ups": [m.view() for m in self.missions.items],
            "outbox": [dict(o) for o in self.outbox],
            "contacts": self.contacts.snapshot(self.backend, self.policy, self.missions),
        }
