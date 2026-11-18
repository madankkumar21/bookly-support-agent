"""A computer-use support rep works one ticket through the screen of the Bookly web app.

    BOOKLY_STORE=1 uv run uvicorn app.server:app --port 8021        (in one terminal)
    uv run python -m evals.cu_ticket_agent --base-url http://localhost:8021 --runs 1

What one run does:
1. Setup, done by code. Reset the store through /api/store/reset, open the page in Chromium (Playwright), and type
   the customer's turns into the chat: order BK-1013 has not arrived (nina.patel@example.com), then accept a person.
   Code checks that ticket T-0001 opened.
2. The computer-use agent (Claude, computer use toolset) plays the support rep. It sees only screenshots of the page
   and acts only with the mouse and keyboard. It must find T-0001 in the staff ticket panel, write a reply, and press
   "Staff replied". It has no HTTP access: the reply reaches the server only through the page's own button.
3. Code checks the result through the API: T-0001 has a reply date and the reply text, and the page sent exactly one
   POST /api/ticket/answer. Then a scripted customer opens "New conversation, same store" and asks again.

Limits: 25 computer actions per run, and a computer-use spend cap summed across every run on this machine
(BOOKLY_CU_BUDGET_USD, default $3.00, logged to logs/cu_spend.jsonl). The support agent behind the chat and Jev run
on the server with their own settings; the Jev budget guard (BOOKLY_JEV_BUDGET_USD) stays on there.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import shutil
import time
import urllib.request
from datetime import datetime

from bookly import config

MODEL = os.getenv("BOOKLY_CU_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("BOOKLY_CU_EFFORT", "medium")
VIEWPORT = {"width": 1600, "height": 1000}  # chat, trace and both store panels fit without page scroll
MAX_ACTIONS = 25
BUDGET_USD = float(os.getenv("BOOKLY_CU_BUDGET_USD", "3.00"))
SPEND_LOG = config.ROOT / "logs" / "cu_spend.jsonl"  # token usage per request; gitignored
MEDIA = config.ROOT / "docs" / "media"
RESULTS = config.ROOT / "evals" / "results" / "cu_ticket_agent"
# USD per million tokens for the default model (Claude Opus 5.5): input, 5-minute cache write, cache read, output.
PRICES = {"claude-opus-5-5": (4.00, 5.00, 0.20, 20.00)}

TICKET = "T-0001"
CUSTOMER_FIRST = "My order BK-1013 hasn't arrived and the tracking stopped updating. My email is nina.patel@example.com."
CUSTOMER_ACCEPTS = ["Yes, please connect me with a person.", "Yes. Please hand this to a person on your team."]
CUSTOMER_RETURN = "Hi, I'm checking on my missing package. Order BK-1013, nina.patel@example.com."

SYSTEM = """You are a Bookly support rep. You work in a web browser, and you see the screen only through screenshots.

The page has three areas. The left column is the customer chat. The right column shows "Behind the reply" (a trace of \
what the assistant and Bookly's code did) and, lower down, "Bookly's systems (simulated)", which lists tickets. A \
ticket that no person has answered has a reply box and a "Staff replied" button under it.

Your task:
1. Find the open ticket in the "Bookly's systems (simulated)" panel. Read the chat on the left to learn what the \
customer needs.
2. Click the ticket's reply box and type a reply to the customer: two to four short sentences, signed "Bookly support". \
Acknowledge the problem with the order number, apologize, and state the next step plainly. Bookly's policy: when \
tracking has stopped well past the estimated delivery date, the package is treated as lost and the team arranges a \
replacement or a refund. Do not promise a refund amount or a date you cannot see on the screen.
3. Click "Staff replied" to send it. Then take one screenshot to check that the ticket row now says a person replied.
4. When the reply is sent, answer with a short text message that starts with DONE. If you cannot do the task, answer \
with a message that starts with FAILED and say why.

Work only in this page. Do not type into the customer chat box. Use few actions: you have at most 25."""

KEYS = {"return": "Enter", "enter": "Enter", "backspace": "Backspace", "tab": "Tab", "escape": "Escape", "esc": "Escape",
        "delete": "Delete", "space": " ", "page_down": "PageDown", "page_up": "PageUp", "home": "Home", "end": "End",
        "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight", "ctrl": "Control",
        "control": "Control", "alt": "Alt", "shift": "Shift", "cmd": "Meta", "super": "Meta", "meta": "Meta"}


# ---------- spend guard ----------

def spent_usd() -> float:
    if not SPEND_LOG.exists():
        return 0.0
    return sum(json.loads(line)["usd"] for line in SPEND_LOG.read_text().splitlines() if line.strip())


def cost_of(usage, model: str) -> float:
    p_in, p_write, p_read, p_out = PRICES.get(model, PRICES["claude-opus-5-5"])
    return ((usage.input_tokens or 0) * p_in + (usage.cache_creation_input_tokens or 0) * p_write
            + (usage.cache_read_input_tokens or 0) * p_read + (usage.output_tokens or 0) * p_out) / 1e6


def log_spend(run_id: str, usage, model: str) -> float:
    usd = cost_of(usage, model)
    SPEND_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SPEND_LOG.open("a") as f:
        f.write(json.dumps({"run": run_id, "model": model, "input": usage.input_tokens,
                            "cache_write": usage.cache_creation_input_tokens, "cache_read": usage.cache_read_input_tokens,
                            "output": usage.output_tokens, "usd": round(usd, 5)}) + "\n")
    return usd


# ---------- the app, through its existing endpoints ----------

def post(base: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(base + path,  # noqa: S310 (local dev server only) data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (local dev server only)
        return json.loads(r.read())


def ticket_state(base: str, ticket_id: str) -> dict | None:
    """Read the shared store's tickets. A new session returns the snapshot and changes nothing in the store."""
    systems = post(base, "/api/session")["systems"]
    return next((t for t in systems["tickets"] if t["ticket_id"] == ticket_id), None)


# ---------- the page ----------

IDLE = "() => !document.getElementById('send').disabled && !document.querySelector('.typing')"


def wait_idle(page, timeout_ms: int = 90_000) -> None:
    page.wait_for_function(IDLE, timeout=timeout_ms)
    page.wait_for_timeout(400)


def customer_says(page, text: str) -> None:
    page.click("#input")
    page.keyboard.type(text, delay=12)
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    wait_idle(page)


def jev_rows(page) -> int:
    return page.locator("#trace .ev.jev").count()


def screenshot_b64(page) -> str:
    with contextlib.suppress(Exception):  # a busy page is still worth a screenshot
        wait_idle(page, timeout_ms=15_000)
    return base64.b64encode(page.screenshot(type="png")).decode()


def key_combo(text: str) -> str:
    return "+".join(KEYS.get(part.strip().lower(), part.strip()) for part in text.split("+"))


def run_action(page, name: str, inp: dict) -> list | str:
    """Execute one computer member at the same pixel coordinates. Returns tool_result content."""
    x, y = (inp.get("coordinate") or [None, None])[:2]
    mods = [key_combo(m) for m in (inp.get("text") or "").split("+") if m] if name.endswith("click") or name == "scroll" else []
    for m in mods:
        page.keyboard.down(m)
    try:
        if name == "screenshot":
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64(page)}}]
        if name == "zoom":
            x0, y0, x1, y1 = inp["region"]
            img = page.screenshot(type="png", clip={"x": x0, "y": y0, "width": max(1, x1 - x0), "height": max(1, y1 - y0)})
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(img).decode()}}]
        if name in ("left_click", "right_click", "middle_click", "double_click", "triple_click"):
            button = {"right_click": "right", "middle_click": "middle"}.get(name, "left")
            clicks = {"double_click": 2, "triple_click": 3}.get(name, 1)
            if x is None:
                page.mouse.down(button=button)
                page.mouse.up(button=button)
            else:
                page.mouse.click(x, y, button=button, click_count=clicks)
        elif name == "left_click_drag":
            sx, sy = inp["start_coordinate"]
            page.mouse.move(sx, sy)
            page.mouse.down()
            page.mouse.move(x, y, steps=10)
            page.mouse.up()
        elif name == "mouse_move":
            page.mouse.move(x, y)
        elif name == "left_mouse_down":
            page.mouse.down()
        elif name == "left_mouse_up":
            page.mouse.up()
        elif name == "type":
            page.keyboard.type(inp["text"], delay=12)
        elif name == "key":
            for _ in range(int(inp.get("repeat") or 1)):
                page.keyboard.press(key_combo(inp["text"]))
        elif name == "scroll":
            if x is not None:
                page.mouse.move(x, y)
            step = 100 * int(inp.get("scroll_amount") or 3)
            dx, dy = {"up": (0, -step), "down": (0, step), "left": (-step, 0), "right": (step, 0)}[inp["scroll_direction"]]
            page.mouse.wheel(dx, dy)
        elif name == "wait":
            page.wait_for_timeout(min(float(inp.get("duration") or 1), 10) * 1000)
        else:
            raise ValueError(f"unsupported action {name}")
    finally:
        for m in reversed(mods):
            page.keyboard.up(m)
    page.wait_for_timeout(250)
    return "OK"


# ---------- the computer-use loop ----------

def cu_loop(client, page, run_id: str, log: list) -> dict:
    tools = [{"type": "computer_toolset_20260801",
              "configs": {"hold_key": {"enabled": False}, "cursor_position": {"enabled": False}}}]
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "Here is the screen now. Work the open ticket."},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64(page)}},
    ]}]
    actions, usd, final_text, stop = 0, 0.0, "", "max_actions"
    while True:
        if spent_usd() >= BUDGET_USD:
            stop = "budget"
            break
        response = client.beta.messages.create(
            model=MODEL, max_tokens=8000, system=SYSTEM, tools=tools, messages=messages,
            thinking={"type": "adaptive"}, output_config={"effort": EFFORT},
            cache_control={"type": "ephemeral"},  # each request re-sends every earlier screenshot: read them from cache
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        usd += log_spend(run_id, response.usage, response.model)
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "refusal":
            stop = "refusal"
            break
        calls = [b for b in response.content if b.type == "tool_use"]
        final_text = " ".join(b.text for b in response.content if b.type == "text").strip() or final_text
        if not calls:
            stop = "done" if final_text.upper().startswith("DONE") else "ended"
            break
        results, failed = [], False
        for b in calls:
            if failed or actions >= MAX_ACTIONS:
                text = ("Not executed: an earlier computer action in this turn failed." if failed
                        else f"Not executed: the cap of {MAX_ACTIONS} actions is reached.")
                results.append({"type": "tool_result", "tool_use_id": b.id, "toolset_name": "computer",
                                "content": text, "is_error": True})
                continue
            actions += 1
            entry = {"n": actions, "action": b.name, "input": {k: v for k, v in b.input.items()}}
            try:
                content = run_action(page, b.name, b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id, "toolset_name": "computer", "content": content})
            except Exception as exc:  # report it to the model, stop the rest of this batch
                failed = True
                entry["error"] = str(exc)[:200]
                results.append({"type": "tool_result", "tool_use_id": b.id, "toolset_name": "computer",
                                "content": f"Error: {str(exc)[:200]}", "is_error": True})
            log.append(entry)
            print(f"  action {actions:2d}: {b.name} {json.dumps(entry['input'])[:120]}")
        messages.append({"role": "user", "content": results})
        if actions >= MAX_ACTIONS:
            break
    return {"actions": actions, "stop": stop, "final_text": final_text, "usd": round(usd, 4), "requests": sum(
        1 for m in messages if m["role"] == "assistant")}


# ---------- one run ----------

def one_run(client, pw, base: str, n: int, headed: bool) -> dict:
    run_id = f"{datetime.now():%Y-%m-%dT%H%M%S}-run{n}"
    out: dict = {"run": run_id, "model": MODEL, "effort": EFFORT, "passed": False, "reasons": []}
    tmp_video = config.ROOT / "logs" / "cu_video_tmp" / run_id  # gitignored; the finished video moves to docs/media
    browser = pw.chromium.launch(headless=not headed)
    context = browser.new_context(viewport=VIEWPORT, record_video_dir=str(tmp_video), record_video_size=VIEWPORT)
    page = context.new_page()
    answers = []  # every POST the PAGE sent to /api/ticket/answer: the only way the reply can reach the server
    page.on("request", lambda r: answers.append(r.post_data) if r.method == "POST" and r.url.endswith("/api/ticket/answer") else None)
    jev_seen = 0
    try:
        # 1. Setup, by code.
        post(base, "/api/store/reset")
        page.goto(base + "/")
        page.wait_for_function("() => typeof sessionId !== 'undefined' && sessionId !== null", timeout=30_000)
        page.wait_for_timeout(800)
        customer_says(page, CUSTOMER_FIRST)
        jev_seen = max(jev_seen, jev_rows(page))
        for accept in CUSTOMER_ACCEPTS:
            if ticket_state(base, TICKET):
                break
            customer_says(page, accept)
            jev_seen = max(jev_seen, jev_rows(page))
        if not ticket_state(base, TICKET):
            out["reasons"].append(f"setup: {TICKET} did not open after the customer accepted a person")
            return out
        page.mouse.move(800, 500)
        print(f"run {n}: setup done, {TICKET} is open. Handing the screen to the computer-use agent.")

        # 2. The computer-use agent, screenshots in, mouse and keyboard out.
        log: list = []
        out["cu"] = cu_loop(client, page, run_id, log)
        out["actions_log"] = log
        page.wait_for_timeout(1000)

        # 3. Checks, by code, through the API.
        t = ticket_state(base, TICKET) or {}
        out["ticket"] = {k: t.get(k) for k in ("ticket_id", "reason_code", "opened_on", "answered_on", "staff_reply")}
        out["page_answer_posts"] = len(answers)
        reply = (t.get("staff_reply") or "").strip()
        if not t.get("answered_on"):
            out["reasons"].append(f"{TICKET} has no reply date")
        if len(reply) < 20:
            out["reasons"].append(f"{TICKET} has no stored reply text (or under 20 characters)")
        elif not any(w in reply.lower() for w in ("bk-1013", "package", "order")):
            out["reasons"].append("the reply does not mention the order or the package")
        if len(answers) != 1:
            out["reasons"].append(f"the page sent {len(answers)} reply requests, expected 1")
        if out["cu"]["stop"] != "done":
            out["reasons"].append(f"the agent stopped with '{out['cu']['stop']}', not DONE")

        # Optional: the customer comes back in a new conversation on the same store.
        if not out["reasons"]:
            page.click("#newchat")
            page.wait_for_function("() => sessionId !== null && document.querySelectorAll('#log .msg').length >= 1", timeout=30_000)
            page.wait_for_timeout(800)
            customer_says(page, CUSTOMER_RETURN)
            out["return_visit_reply"] = page.locator("#log .msg.bot").last.inner_text()
            jev_seen = max(jev_seen, jev_rows(page))
            page.wait_for_timeout(2500)
        out["jev_rows_seen"] = jev_seen
        out["passed"] = not out["reasons"]
        return out
    except Exception as exc:
        out["reasons"].append(f"error: {type(exc).__name__}: {str(exc)[:300]}")
        return out
    finally:
        video = page.video
        context.close()
        browser.close()
        if video:
            MEDIA.mkdir(parents=True, exist_ok=True)
            dest = MEDIA / f"cu_ticket_{run_id}.webm"
            shutil.move(video.path(), dest)
            out["video"] = str(dest.relative_to(config.ROOT))
            out["video_bytes"] = dest.stat().st_size
        shutil.rmtree(tmp_video, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://localhost:8021")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    args = ap.parse_args()
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set (see .env.example).")
    if spent_usd() >= BUDGET_USD:
        raise SystemExit(f"computer-use budget of ${BUDGET_USD:.2f} is used up (${spent_usd():.2f} in {SPEND_LOG.name}).")
    from playwright.sync_api import sync_playwright

    client = config.make_client(timeout=180)
    RESULTS.mkdir(parents=True, exist_ok=True)
    runs = []
    with sync_playwright() as pw:
        for n in range(1, args.runs + 1):
            started = time.time()
            r = one_run(client, pw, args.base_url.rstrip("/"), n, args.headed)
            r["seconds"] = round(time.time() - started)
            runs.append(r)
            print(f"run {n}: {'PASS' if r['passed'] else 'FAIL'} {r['reasons'] or ''} · ${r.get('cu', {}).get('usd', 0):.3f}")
            (RESULTS / f"{r['run']}.json").write_text(json.dumps(r, indent=2))
    print(f"{len(runs)} runs: {sum(r['passed'] for r in runs)} passed · computer-use spend on this machine so far ${spent_usd():.3f}")


if __name__ == "__main__":
    main()
