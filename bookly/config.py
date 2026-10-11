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

# Loop limits.
MAX_TOOL_STEPS_PER_TURN = 6
MAX_CUSTOMER_TURNS = 14
MAX_NEEDS_INPUT_PER_FIELD = 2  # after this many unanswered asks for one field, hand off
