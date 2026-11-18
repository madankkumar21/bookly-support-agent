"""Runtime configuration. Model IDs and the fixed clock live here."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
PROMPTS = Path(__file__).resolve().parent / "prompts"
PROCEDURES = Path(__file__).resolve().parent / "procedures"

load_dotenv(ROOT / ".env")

# Fixed clock so every run (and every eval) sees the same order ages.
TODAY = date.fromisoformat(os.getenv("BOOKLY_TODAY", "2026-10-10"))

POLICY_PATH = DATA / "policy.yaml"
POLICY_TEXT_PATH = DATA / "policy_text.yaml"
ORDERS_PATH = DATA / "orders.json"

# Agent model: Sonnet 5.5 is the production-like default (latency and cost).
AGENT_MODEL = os.getenv("BOOKLY_AGENT_MODEL", "claude-sonnet-5-5")
AGENT_EFFORT = os.getenv("BOOKLY_AGENT_EFFORT", "low")
AGENT_MAX_TOKENS = int(os.getenv("BOOKLY_AGENT_MAX_TOKENS", "4000"))

# Simulated customer for evals.
SIM_MODEL = os.getenv("BOOKLY_SIM_MODEL", "claude-haiku-5-5")

# Intent router, off by default (bookly/router.py). Below the threshold it loads every procedure.
ROUTER_ENABLED = os.getenv("BOOKLY_ROUTER", "0") == "1"
ROUTER_MODEL = os.getenv("BOOKLY_ROUTER_MODEL", "claude-haiku-5-5")
ROUTER_THRESHOLD = float(os.getenv("BOOKLY_ROUTER_THRESHOLD", "0.6"))
ROUTER_TIMEOUT_S = 5.0
ROUTER_ENGINE = os.getenv("BOOKLY_ROUTER_ENGINE", "haiku")  # haiku | jev (bookly/jev_router.py)

# Jev, TypeSafe's decision model, and the cross-session store. Both off by default (docs/JEV.md).
# Jev answers typed yes/no questions with a probability; code decides what to do with the answers.
STORE_ENABLED = os.getenv("BOOKLY_STORE", "0") == "1"  # customer memory, recommendations, follow-ups
# Reship journey (docs/CU_JOURNEY.md). Needs the store. Off by default: with it off nothing below changes.
RESHIP_ENABLED = os.getenv("BOOKLY_RESHIP", "0") == "1"
DELAY_WATCH_BUSINESS_DAYS = 1  # a delay_watch follow-up is due this many business days after it opens


def jev_key_present() -> bool:
    return bool(os.getenv("TYPESAFE_API_KEY", "").strip())


def startup_notes() -> list[str]:
    """Settings that run without an error and do less than the developer expects. The web server logs them when it starts."""
    notes = []
    if not jev_key_present():
        if STORE_ENABLED:
            notes.append("TYPESAFE_API_KEY is not set: Jev is never called. Tastes are not saved, typed follow-up "
                         "answers are not read, and the last-contact mood stays unknown.")
        if ROUTER_ENABLED and ROUTER_ENGINE == "jev":
            notes.append("TYPESAFE_API_KEY is not set: the Jev router cannot answer, so every procedure loads.")
    if ROUTER_ENGINE == "jev" and not ROUTER_ENABLED:
        notes.append("BOOKLY_ROUTER_ENGINE=jev has no effect: the router is off. Set BOOKLY_ROUTER=1 as well.")
    if ROUTER_ENGINE not in ("haiku", "jev"):
        notes.append(f"BOOKLY_ROUTER_ENGINE={ROUTER_ENGINE!r} is not a known engine: the Haiku router is used.")
    return notes
JEV_MODEL = os.getenv("BOOKLY_JEV_MODEL", "jev-1.14.0")  # pinned: the bands in judgments.py were read against it
JEV_BUDGET_USD = float(os.getenv("BOOKLY_JEV_BUDGET_USD", "2.00"))  # hard stop across every run on this machine
JEV_USD_PER_MTOK_INPUT = 0.042  # output is free (docs.typesafe.ai/models, 2026-11-13)
JEV_TIMEOUT_S = 5.0
JEV_LOG = ROOT / "logs" / "jev_calls.jsonl"  # every request payload and answer; gitignored
CATALOG_PATH = DATA / "catalog.json"
FOLLOW_UP_GRACE_DAYS = 2  # a refund follow-up is due this many days after the stated refund time
LOST_PACKAGE_CHECK_DAYS = 3  # a lost-package follow-up is due this many days after the hand-off
FOLLOW_UP_EXPIRES_DAYS = 14  # an unanswered follow-up closes (refund) or escalates (lost package)

# Only needed when the API key is not scoped to a workspace.
WORKSPACE_ID = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()


def make_client(timeout: float = 90, max_retries: int = 2):
    """One place to build the Anthropic client, so every caller sends the same headers."""
    import anthropic

    headers = {"anthropic-workspace-id": WORKSPACE_ID} if WORKSPACE_ID else None
    return anthropic.Anthropic(timeout=timeout, max_retries=max_retries, default_headers=headers)


# Loop limits.
MAX_TOOL_STEPS_PER_TURN = 6
MAX_NEEDS_INPUT_PER_FIELD = 2  # after this many unanswered asks for one field, hand off
MAX_LOOKUP_MISSES = 3  # failed order lookups per conversation before code locks get_order
