"""Chat with the Bookly agent in the terminal, with an inline trace of every tool call and gate decision.

    uv run python cli.py                 # interactive
    uv run python cli.py --script demo   # play a scripted conversation from demo/<name>.txt
    uv run python cli.py --no-trace      # hide the trace

At a confirmation card, type /confirm or /cancel to press the buttons (or reply in words).
When options are shown, type the number to pick one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bookly.agent import Agent, TurnResult

DIM, BOLD, CYAN, GREEN, RED, YELLOW, RESET = "\033[2m", "\033[1m", "\033[36m", "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def short(value, n=110) -> str:
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


def summarize_result(tool: str, r: dict) -> str:
    if tool == "get_order":
        return f"{r.get('status')}" + (f" · {r['order']['status']}" if r.get("order") else "")
    if tool == "check_return_eligibility":
        if r.get("status") == "blocked":
            return f"blocked: {r.get('reason')}"
        d = r.get("decision")
        extra = {"needs_input": f" ({r.get('field')})", "ineligible": f" ({r.get('reason_code')})",
                 "needs_human": f" (${r.get('amount')})"}.get(d, f" ${r.get('amount')} · {r.get('quote_id')}")
        return f"{d}{extra}"
    if tool == "create_return":
        return f"{r.get('status')}" + (f" · {r.get('rma_id')} / {r.get('refund_id')}" if r.get("rma_id") else f" · {r.get('reason', '')}")
    if tool == "search_policy":
        return f"{len(r.get('passages', []))} passage(s): " + ", ".join(p["id"] for p in r.get("passages", []))
    return short(r.get("status", r))


def print_trace(events: list[dict]) -> None:
    for e in events:
        k = e["kind"]
        if k == "tool_call":
            args = ", ".join(f"{a}={short(v, 40)}" for a, v in e["input"].items())
            print(f"{DIM}  → {e['tool']}({args}){RESET}")
        elif k == "tool_result":
            colour = RED if e["result"].get("status") == "blocked" else DIM
            print(f"{colour}    ← {summarize_result(e['tool'], e['result'])}{RESET}")
        elif k == "gate":
            colour = GREEN if e["allowed"] else RED
            print(f"{colour}  ⛨ gate create_return: {'ALLOWED' if e['allowed'] else 'BLOCKED'} · {e['reason']}{RESET}")
        elif k == "confirmation":
            print(f"{YELLOW}  ✓ customer reply to card read by code: {e['signal']} ({e['source']}){RESET}")
        elif k == "claim_check":
            print(f"{RED}  ! claim check replaced an unbacked refund claim{RESET}")
        elif k == "api_call":
            print(f"{DIM}  · {e['model']} {e['stop_reason']} {e['latency_ms']} ms{RESET}")


def print_turn(t: TurnResult, trace: bool) -> None:
    if trace:
        print_trace(t.events)
    print(f"{BOLD}{CYAN}Bookly:{RESET} {t.reply}")
    for i, o in enumerate(t.options, 1):
        print(f"   {CYAN}[{i}]{RESET} {o}")
    if t.card:
        c = t.card
        print(f"{YELLOW}  ┌─ Please confirm ({c['quote_id']}) ───────────────{RESET}")
        print(f"{YELLOW}  │ {', '.join(c['items'])} · {c['reason']} · {c['amount']}{RESET}")
        print(f"{YELLOW}  │ {c['terms']}{RESET}")
        print(f"{YELLOW}  └─ /confirm   /cancel{RESET}")
    if trace:
        u = t.usage
        print(f"{DIM}  turn: {u['api_calls']} call(s), {u['latency_ms']} ms, ${u['cost_usd']:.4f}{RESET}")


def parse_input(raw: str, last: TurnResult | None) -> tuple[str, str | None]:
    raw = raw.strip()
    if raw in ("/confirm", "/cancel"):
        return "", raw[1:]
    if last and last.options and raw.isdigit() and 1 <= int(raw) <= len(last.options):
        return last.options[int(raw) - 1], None
    return raw, None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", help="name of a file in demo/ with one customer message per line")
    ap.add_argument("--no-trace", action="store_true")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    trace = not args.no_trace

    agent = Agent(**({"model": args.model} if args.model else {}))
    print(f"{BOLD}Bookly support{RESET} {DIM}(model {agent.model}; /quit to exit){RESET}")
    last: TurnResult | None = None

    lines = None
    if args.script:
        path = Path(__file__).parent / "demo" / f"{args.script}.txt"
        lines = [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]

    while True:
        if lines is not None:
            if not lines:
                break
            raw = lines.pop(0)
            print(f"{BOLD}You:{RESET} {raw}")
        else:
            try:
                raw = input(f"{BOLD}You:{RESET} ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
        if raw.strip() in ("/quit", "/exit"):
            break
        text, button = parse_input(raw, last)
        last = agent.handle(text, button=button)
        print_turn(last, trace)

    u = agent.usage.as_dict()
    print(f"{DIM}session: {u['api_calls']} API calls, ${u['cost_usd']:.4f}, returns created: {len(agent.backend.ledger)}{RESET}")


if __name__ == "__main__":
    sys.exit(main())
