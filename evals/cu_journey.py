"""One customer, three visits, and a computer-use rep in the order console (docs/CU_JOURNEY.md).

    BOOKLY_STORE=1 BOOKLY_RESHIP=1 uv run uvicorn app.server:app --port 8021        (in one terminal)
    uv run python -m evals.cu_journey --base-url http://localhost:8021 --runs 2

What one run does. Code types every customer line (scripted free text) and clicks every clock button.
1. Visit 1 (store date 2026-10-10). Order BK-1020 is two days late, not lost. The customer ends angry.
2. Code clicks "+1 day" three times (2026-10-13: two business days after the last scan, inside the lost window),
   then "New conversation, same store". Visit 2: still not here. The customer declines the person offer and leaves.
3. Code clicks "+1 day" four times (2026-10-17: five business days, so lost by the existing _likely_lost rule),
   then "New conversation, same store". Visit 3: still nothing. Code writes a reship_request.
4. Between chat turns (a chat turn holds the store lock), the computer-use agent works the request in the order
   console (/admin). It sees only screenshots and acts only with the mouse and keyboard.
5. The customer sends one more line, and the chat relays the confirmation that code wrote. The console's
   priority reship opened one reship_followup staff ticket with a code-built handoff summary, and code shows a
   "Handed to staff" note after the confirmation.

Code checks the store after each beat (moods, decisions, follow-ups, the reship) and counts the console's POSTs.
Caps: 25 computer actions per run; the shared computer-use spend cap (BOOKLY_CU_BUDGET_USD, default $3.00);
the server's Jev budget guard stays on.

Video: the chat page and the console page are recorded at the same time (two Playwright pages, one context).
Both raw recordings are saved, plus one combined video that shows the chat, then the console while computer use
runs, then the chat again, on one continuous timeline (no time is cut).
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime

from bookly import config
from bookly.jev import spent_usd as jev_spent_usd
from evals import cu_ticket_agent as cu

VIEWPORT = cu.VIEWPORT
RESULTS = config.ROOT / "evals" / "results" / "cu_journey"
ORDER, EMAIL = "BK-1020", "riley.morgan@example.com"

VISIT_1 = [f"Where is my order {ORDER}? It was due on the 8th. My email is {EMAIL}.",
           "This is ridiculous. I'm done waiting on you people."]
VISIT_2 = [f"It's still not here and nothing has changed on the tracking. Order {ORDER}, {EMAIL}.",
           "No. I don't want to talk to anyone, I just want my damn book."]
# The first script's line had no "damn". Jev read it as concerned (P(angry) 0.16-0.17, below the 0.6 bar) on two calls, so the
# mood beat could not fire. One word of strong language puts it at 0.96. Mood rules and thresholds are unchanged.
VISIT_3 = [f"Still nothing has arrived, and the tracking hasn't moved in a week. Order {ORDER}, {EMAIL}."]
AFTER_CONSOLE = "Okay. Has it actually been sent?"
JUMP_1, JUMP_2 = 3, 4  # days; see the dates in the docstring

SYSTEM = """You are a Bookly support rep. You work in Bookly's order console in a web browser, and you see the screen \
only through screenshots.

Your task:
1. On "Home / Work Queue", find the pending reship request. Note its order number and its reason code.
2. Open "Order Search" in the left menu and search for that order number.
3. On the order page, open the "Actions" menu and choose "Reship Order".
4. Select the reason code that matches the request, click "Submit Reship", then click OK in the confirmation box.
5. Take one screenshot to check that the page says RESHIP CREATED.
6. Then answer with a short text message that starts with DONE and gives the reship id. If the console rejects \
the action or anything does not match the request, do not try again: answer with a message that starts with \
FAILED and say why.

The page updates at once after a click, so you do not need to wait. Work only in this page. Process only the order in the request. Use few actions: you have at most 25, and screenshots and zooms count."""


def post(base: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), method="POST",  # noqa: S310
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (local dev server only)
        return json.loads(r.read())


def state(base: str) -> dict:
    """The shared store's snapshot. A new session returns it and changes nothing in the store."""
    d = post(base, "/api/session")
    return {"store": d["store"], "systems": d["systems"]}


def plain_shot(page) -> str:
    page.wait_for_timeout(300)
    return base64.b64encode(page.screenshot(type="png")).decode()


def click_days(page, days: int) -> None:
    for _ in range(days):
        page.click('#storebar [data-days="1"]')
        page.wait_for_timeout(700)


def new_conversation(page) -> None:
    page.click("#newchat")
    page.wait_for_function("() => sessionId !== null && document.querySelectorAll('#log .msg').length >= 1",
                           timeout=30_000)
    page.wait_for_timeout(1200)


class Turns:
    """Chat responses, collected in the page's event handler and parsed later (no page calls inside a handler)."""

    def __init__(self) -> None:
        self.raw, self._parsed = [], {}

    def __len__(self) -> int:
        return len(self.raw)

    def __getitem__(self, key):
        idx = range(len(self.raw))[key]
        if isinstance(idx, int):
            return self._get(idx)
        return [self._get(i) for i in idx]

    def _get(self, i: int) -> dict:
        if i not in self._parsed:
            self._parsed[i] = self.raw[i].json()
        return self._parsed[i]


def events_of(turns, start: int) -> list:
    return [e for t in turns[start:] for e in t.get("events", [])]


def check(out: dict, beat: str, ok: bool, what: str) -> None:
    out["checks"].append({"beat": beat, "ok": bool(ok), "what": what})
    if not ok:
        out["reasons"].append(f"{beat}: {what}")


def mood(snap: dict) -> str:
    return (snap["store"]["contacts"].get(EMAIL) or {}).get("mood", "none")


def watches(snap: dict) -> list:
    return [m for m in snap["store"]["follow_ups"] if m["kind"] == "delay_watch"]


HOLD_S = 3  # the combined video holds its last frame this long, so the handoff card and note can be read


def combine(chat_video, console_video, t_cu0: float, t_cu1: float, chat0: float, console0: float, dest) -> bool:
    """One continuous timeline: chat until computer use starts, the console while it runs, then the chat."""
    a, b0, b1, c = t_cu0 - chat0, t_cu0 - console0, t_cu1 - console0, t_cu1 - chat0
    graph = (f"[0:v]split[x][y];[x]trim=0:{a:.2f},setpts=PTS-STARTPTS[p];"
             f"[1:v]trim={b0:.2f}:{b1:.2f},setpts=PTS-STARTPTS[q];[y]trim=start={c:.2f},setpts=PTS-STARTPTS[r];"
             f"[p][q][r]concat=n=3:v=1,tpad=stop_mode=clone:stop_duration={HOLD_S}[out]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(chat_video), "-i", str(console_video),
           "-filter_complex", graph, "-map", "[out]", "-c:v", "libx264", "-crf", "30", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", str(dest)]
    return shutil.which("ffmpeg") is not None and subprocess.run(cmd, check=False).returncode == 0


def one_run(client, pw, base: str, n: int, headed: bool) -> dict:
    run_id = f"{datetime.now():%Y-%m-%dT%H%M%S}-run{n}"
    out: dict = {"run": run_id, "model": cu.MODEL, "effort": cu.EFFORT, "passed": False, "reasons": [], "checks": [],
                 "script": {"visit_1": VISIT_1, "visit_2": VISIT_2, "visit_3": VISIT_3, "after_console": AFTER_CONSOLE,
                            "jumps_days": [JUMP_1, JUMP_2]}}
    tmp_video = config.ROOT / "logs" / "cu_video_tmp" / run_id  # gitignored; finished videos move to docs/media
    jev_before = jev_spent_usd()
    browser = pw.chromium.launch(headless=not headed)
    context = browser.new_context(viewport=VIEWPORT, record_video_dir=str(tmp_video), record_video_size=VIEWPORT)
    page = context.new_page()
    chat0 = time.monotonic()
    console = context.new_page()
    console0 = time.monotonic()
    turns = Turns()  # every /api/chat response the chat page received
    reship_posts: list = []  # every POST the CONSOLE page sent to /admin/api/reship
    page.on("response", lambda r: turns.raw.append(r) if r.url.endswith("/api/chat") and r.ok else None)
    console.on("request", lambda r: reship_posts.append(r.post_data)
               if r.method == "POST" and r.url.endswith("/admin/api/reship") else None)
    t_cu0 = t_cu1 = None
    try:
        post(base, "/api/store/reset")
        page.bring_to_front()
        page.goto(base + "/")
        page.wait_for_function("() => typeof sessionId !== 'undefined' && sessionId !== null", timeout=30_000)
        page.wait_for_timeout(800)

        # ---- visit 1 ----
        mark = len(turns)
        for line in VISIT_1:
            cu.customer_says(page, line)
        s = state(base)
        w = watches(s)
        out["visit_1"] = {"today": s["store"]["today"], "mood": mood(s), "watches": w,
                          "replies": [t["reply"] for t in turns[mark:]]}
        check(out, "visit 1", mood(s) == "angry", f"stored mood is angry (got {mood(s)})")
        check(out, "visit 1", len(w) == 1 and w[0]["status"] == "scheduled", "one delay_watch is scheduled")
        check(out, "visit 1", not s["systems"]["tickets"], "no ticket was opened")

        # ---- clock, visit 2 ----
        click_days(page, JUMP_1)
        s = state(base)
        check(out, "jump 1", s["store"]["today"] == "2026-10-13" and watches(s)[0]["status"] == "awaiting_reply",
              "today is 2026-10-13 and the delay_watch email was sent")
        new_conversation(page)
        mark = len(turns)
        for line in VISIT_2:
            cu.customer_says(page, line)
        s, ev = state(base), events_of(turns, mark)
        contact = [e for e in ev if e["kind"] == "return_contact"]
        read = [e for e in ev if e["kind"] == "jev" and e.get("purpose") == "follow_up"]
        w = watches(s)
        out["visit_2"] = {"today": s["store"]["today"], "mood": mood(s), "watches": w, "return_contact": contact,
                          "follow_up_reads": read, "replies": [t["reply"] for t in turns[mark:]]}
        check(out, "visit 2", contact and contact[0]["decision"] == "early_escalation",
              "code read the last contact as early_escalation (a person is offered)")
        check(out, "visit 2", read and read[0]["decision"] == "still_missing" and read[0]["answers"]["not_arrived"] >= 0.7,
              "Jev read 'not arrived' and code decided still_missing")
        check(out, "visit 2", len(w) == 2 and w[0]["status"] == "closed_still_missing" and w[1]["status"] == "scheduled",
              "the first delay_watch closed and a new one is scheduled")
        check(out, "visit 2", mood(s) == "angry", f"stored mood stays angry (got {mood(s)})")
        check(out, "visit 2", not s["systems"]["tickets"] and not s["systems"]["reship_requests"],
              "no ticket and no reship request (the customer declined; not lost yet)")

        # ---- clock, visit 3 ----
        click_days(page, JUMP_2)
        s = state(base)
        check(out, "jump 2", s["store"]["today"] == "2026-10-17" and watches(s)[1]["status"] == "awaiting_reply",
              "today is 2026-10-17 and the second delay_watch email was sent")
        new_conversation(page)
        mark = len(turns)
        for line in VISIT_3:
            cu.customer_says(page, line)
        s, ev = state(base), events_of(turns, mark)
        reqs = s["systems"]["reship_requests"]
        decided = [e for e in ev if e["kind"] == "reship"]
        out["visit_3"] = {"today": s["store"]["today"], "mood_before": out["visit_2"]["mood"], "reship_events": decided,
                          "requests": reqs, "replies": [t["reply"] for t in turns[mark:]]}
        check(out, "visit 3", len(reqs) == 1 and reqs[0]["order_id"] == ORDER and reqs[0]["status"] == "pending",
              "code wrote one pending reship_request for BK-1020")
        check(out, "visit 3", reqs and reqs[0]["priority"] is True, "the priority flag is set (last visit ended angry)")
        check(out, "visit 3", not s["systems"]["tickets"], "no lost-package ticket")
        if not reqs:
            return out

        # ---- computer use in the console, between chat turns ----
        console.bring_to_front()
        console.goto(base + "/admin")
        console.wait_for_timeout(1000)
        t_cu0 = time.monotonic()
        log: list = []
        out["cu"] = cu.cu_loop(client, console, run_id, log, system=SYSTEM,
                               first_text="Here is the screen now. Work the pending request.", shot=plain_shot)
        out["actions_log"] = log
        console.wait_for_timeout(2000)
        t_cu1 = time.monotonic()
        s = state(base)
        rs, posts = s["systems"]["reships"], s["systems"]["console_posts"]
        out["console"] = {"reships": rs, "server_console_posts": posts, "page_reship_posts": len(reship_posts)}
        check(out, "console", len(rs) == 1 and rs[0]["order_id"] == ORDER, "exactly one reship, on BK-1020")
        check(out, "console", len(posts) == 1 and len(reship_posts) == 1,
              f"exactly one console POST (server saw {len(posts)}, page sent {len(reship_posts)})")
        check(out, "console", out["cu"]["stop"] == "done", f"the agent ended with DONE (got {out['cu']['stop']})")
        follow = [t for t in s["systems"]["tickets"] if t["reason_code"] == "reship_followup"]
        out["console"]["followup_tickets"] = follow
        check(out, "console", len(follow) == 1 and follow[0]["payload"].get("priority") is True
              and len(s["systems"]["tickets"]) == 1 and rs and follow[0]["payload"].get("reship_id") == rs[0]["reship_id"]
              and rs[0].get("ticket_id") == follow[0]["ticket_id"],
              "code opened exactly one priority reship_followup ticket for the reship, and no other ticket")
        handoff = follow[0]["payload"].get("handoff") if follow else None
        want_handoff = {"header": f"{ORDER} · Riley Morgan · Priority follow-up",
                        "contacts": ["10/10 — 2 days late", "10/13 — still missing; declined a person",
                                     "10/17 — lost (no scan since 10/9)"],
                        "done": f"Reship {rs[0]['reship_id'] if rs else '?'} issued in the order console on 10/17.",
                        "next": "Confirm the replacement shipped, then check in with the customer."}
        check(out, "console", handoff == want_handoff, f"the ticket carries the code-built handoff summary (got {handoff})")

        # ---- back to the chat: the confirmation code wrote ----
        page.bring_to_front()
        mark = len(turns)
        cu.customer_says(page, AFTER_CONSOLE)
        reply = turns[-1]["reply"] if len(turns) > mark else ""
        notes = turns[-1].get("notes", []) if len(turns) > mark else []
        out["visit_3"]["confirmation_reply"], out["visit_3"]["notes"] = reply, notes
        check(out, "confirmation", rs and rs[0]["reship_id"] in reply and "October 10" in reply and "October 13" in reply,
              "the chat relayed the reship id and the code-written citation of both earlier visits")
        want = {"kind": "handoff", "label": "Handed to staff",
                "text": f"Priority follow-up · ticket {follow[0]['ticket_id']} · reship {rs[0]['reship_id']}"} \
            if follow and rs else None
        check(out, "confirmation", want is not None and notes == [want],
              f"code showed one 'Handed to staff' note after the confirmation (got {notes})")
        # Final screen: the handoff card in view in the systems panel, the note at the bottom of the chat.
        page.evaluate("document.querySelector('#systems .handoff')?.scrollIntoView({block: 'nearest'})")
        page.wait_for_timeout(3000)
        out["passed"] = not out["reasons"]
        return out
    except Exception as exc:
        out["reasons"].append(f"error: {type(exc).__name__}: {str(exc)[:300]}")
        return out
    finally:
        out["jev_usd"] = round(jev_spent_usd() - jev_before, 5)
        videos = (page.video, console.video)
        context.close()
        browser.close()
        cu.MEDIA.mkdir(parents=True, exist_ok=True)
        dests = []
        for v, tag in zip(videos, ("chat", "console"), strict=True):
            if v:
                dest = cu.MEDIA / f"cu_journey_{run_id}-{tag}.webm"
                shutil.move(v.path(), dest)
                dests.append(dest)
        out["videos"] = {d.name: d.stat().st_size for d in dests}
        if len(dests) == 2 and t_cu0 and t_cu1:
            combined = cu.MEDIA / f"cu_journey_{run_id}.mp4"
            if combine(dests[0], dests[1], t_cu0, t_cu1, chat0, console0, combined):
                out["videos"][combined.name] = combined.stat().st_size
        shutil.rmtree(tmp_video, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://localhost:8021")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    args = ap.parse_args()
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set (see .env.example).")
    if cu.spent_usd() >= cu.BUDGET_USD:
        raise SystemExit(f"computer-use budget of ${cu.BUDGET_USD:.2f} is used up (${cu.spent_usd():.2f}).")
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
            print(f"run {n}: {'PASS' if r['passed'] else 'FAIL'} {r['reasons'] or ''} · computer use "
                  f"${r.get('cu', {}).get('usd', 0):.3f} · Jev ${r['jev_usd']:.4f} · {r['seconds']} s")
            (RESULTS / f"{r['run']}.json").write_text(json.dumps(r, indent=2))
    print(f"{len(runs)} runs: {sum(r['passed'] for r in runs)} passed · computer-use spend on this machine so far "
          f"${cu.spent_usd():.3f}")


if __name__ == "__main__":
    main()
