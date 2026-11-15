"""Run the multi-session journeys: several conversations and clock ticks on one shared store.

    uv run python -m evals.run_journeys --k 3
    uv run python -m evals.run_journeys --only J1,J6 --k 1 --label smoke

Each journey run gets a fresh Store (bookly/store.py). Each session in it is a new Agent and a new simulated
customer; a tick moves the store's clock and runs the scheduled follow-up check. Every session is graded by
the same deterministic checks as the single-conversation suite (evals/checks.py), on what that session added.
The journey is then graded on the store's end state.

Needs both keys: ANTHROPIC_API_KEY (agent and simulated customer) and TYPESAFE_API_KEY (Jev).
Writes evals/results/<date>-<label>/: report.md, summary.json, transcripts.jsonl.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import anthropic
import yaml

from bookly import config
from bookly import recommend as recommender
from bookly.agent import Agent
from bookly.jev import Jev
from bookly.policy import Policy
from bookly.store import Store
from evals.checks import check_run
from evals.run_evals import MAX_CUSTOMER_TURNS, Budget, render_expected
from evals.simulator import Simulator, SimulatorRefused

HERE = Path(__file__).resolve().parent


def load_journeys(only: set[str] | None) -> list[dict]:
    journeys = yaml.safe_load((HERE / "journeys.yaml").read_text())["journeys"]
    return [j for j in journeys if not only or j["id"] in only]


def system_text(agent: Agent) -> str:
    """Every system-role message the model saw in one session, as one string."""
    out = [agent.system]
    for m in agent.messages:
        if m["role"] == "system":
            out.append(m["content"] if isinstance(m["content"], str) else " ".join(b["text"] for b in m["content"]))
    return "\n".join(out)


def check_recommend(exp: dict, trace: list[dict], replies: list[str], picked: set[str]) -> tuple[dict, list[str]]:
    """The extra checks a session can ask for under expected.recommend."""
    checks, notes = {}, []
    genres = {b["title"]: set(b["genres"]) for b in recommender.catalog()}
    called = any(e["kind"] == "tool_call" and e["tool"] == "recommend_books" for e in trace)
    if exp.get("called"):
        checks["recommend_called"] = called
    elif exp.get("called") is False:  # the customer never asked: no tool call, and no book offered from the model's own head
        offered = [e for e in trace if e["kind"] == "recommend_check"]
        checks["recommend_not_called"] = not called
        checks["no_book_offered"] = not offered
        if called:
            notes.append("recommend_books was called, but the customer never asked for a recommendation")
        if offered:
            notes.append(f"the model offered a book unasked: {offered[0]['titles']}")
    if exp.get("names_a_pick"):
        named = recommender.titles_in("\n".join(replies)) & picked
        fired = [e for e in trace if e["kind"] == "recommend_check"]
        checks["names_a_pick"] = bool(named)
        checks["no_unlisted_book_named"] = not fired
        if fired:
            notes.append(f"the model named a book the system did not hand it: {fired[0]['titles']}")
        if not named:
            notes.append(f"no pick named in the replies (picks: {sorted(picked)})")
    bad = sorted(picked & set(exp.get("picks_exclude_titles", [])))
    bad += sorted(t for t in picked if genres.get(t, set()) & set(exp.get("picks_exclude_genres", [])))
    if "picks_exclude_titles" in exp or "picks_exclude_genres" in exp:
        checks["picks_respect_filters"] = not bad
        if bad:
            notes.append(f"picks that should have been filtered out: {bad}")
    if "history" in exp:
        histories = [e.get("history") for e in trace if e["kind"] == "jev" and e.get("purpose") == "recommend"]
        checks["history_is_verified_orders_only"] = bool(histories) and all(h == exp["history"] for h in histories)
        if not checks["history_is_verified_orders_only"]:
            notes.append(f"history sent to Jev: {histories}, expected {exp['history']}")
    return checks, notes


def check_return_contact(want: str, trace: list[dict]) -> tuple[dict, list[str]]:
    """What code decided about the customer's last contact when the order was verified (bookly/contact.py).
    'none' also passes when there was no earlier contact to read."""
    got = [e["decision"] for e in trace if e["kind"] == "return_contact"] or ["none"]
    ok = got == [want]
    return {"return_contact": ok}, [] if ok else [f"return_contact: expected {want}, got {got}"]


def check_journey(expected: dict, snapshot: dict, backend_snapshot: dict, system_texts: list[str]) -> dict:
    """Grade the store's end state. Pure: takes snapshots, so saved runs can be re-graded."""
    checks, notes = {}, []
    counts = {"ledger_total": len(backend_snapshot["returns"]), "tickets_total": len(backend_snapshot["tickets"]),
              "outbox_total": len(snapshot["outbox"])}
    for key, got in counts.items():
        if key in expected:
            checks[key] = got == expected[key]
            if not checks[key]:
                notes.append(f"{key}: expected {expected[key]}, got {got}")
    if expected.get("memory_empty"):
        checks["memory_empty"] = not snapshot["memory"]
        if snapshot["memory"]:
            notes.append(f"memory should be empty: {snapshot['memory']}")
    for email, want in (expected.get("memory") or {}).items():
        got = snapshot["memory"].get(email, {"likes": [], "dislikes": []})
        ok = set(want.get("likes_include", [])) <= set(got["likes"]) and set(want.get("dislikes_include", [])) <= set(got["dislikes"])
        checks["memory"] = checks.get("memory", True) and ok
        if not ok:
            notes.append(f"memory for {email}: expected at least {want}, got {got}")
    for want in expected.get("follow_ups", []):
        hit = [m for m in snapshot["follow_ups"] if m["order_id"] == want["order_id"]]
        ok = len(hit) == 1 and hit[0]["status"] == want["status"]
        checks["follow_ups"] = checks.get("follow_ups", True) and ok
        if not ok:
            notes.append(f"follow-up for {want['order_id']}: expected {want['status']}, got {[m['status'] for m in hit]}")
    for email, want in (expected.get("contacts") or {}).items():
        got = snapshot.get("contacts", {}).get(email, {})
        ok = all(got.get(k) == v for k, v in want.items())
        checks["contacts"] = checks.get("contacts", True) and ok
        if not ok:
            notes.append(f"last contact for {email}: expected {want}, got { {k: got.get(k) for k in want} }")
    if "last_ticket" in expected:  # fields of the newest ticket; previous_ticket and priority are in its payload
        t = backend_snapshot["tickets"][-1] if backend_snapshot["tickets"] else {}
        flat = {"reason_code": t.get("reason_code"), "priority": (t.get("payload") or {}).get("priority"),
                "previous_ticket": ((t.get("payload") or {}).get("previous_ticket") or {}).get("ticket_id")}
        ok = all(flat.get(k) == v for k, v in expected["last_ticket"].items())
        checks["last_ticket"] = ok
        if not ok:
            notes.append(f"the newest ticket: expected {expected['last_ticket']}, got {flat}")
    if "last_ticket_cites" in expected:
        tickets = backend_snapshot["tickets"]
        origins = [f["origin"] for f in (tickets[-1]["payload"].get("follow_ups") or [])] if tickets else []
        checks["last_ticket_cites"] = expected["last_ticket_cites"] in origins
        if not checks["last_ticket_cites"]:
            notes.append(f"the newest ticket does not carry a follow-up with origin {expected['last_ticket_cites']}")
    for needle in expected.get("system_must_not_contain", []):
        leaked = any(needle.lower() in t.lower() for t in system_texts)
        checks["system_text_clean"] = checks.get("system_text_clean", True) and not leaked
        if leaked:
            notes.append(f"a system message contains {needle!r}")
    return {"passed": all(checks.values()), "checks": checks, "notes": notes}


def run_session(spec: dict, store: Store, args, client: anthropic.Anthropic) -> dict:
    b = store.backend
    before = (len(b.ledger), len(b.tickets), len(b.password_resets))
    agent = Agent(client=client, model=args.model, effort=args.effort, store=store)
    last_email = store.outbox[-1]["text"] if store.outbox else "(no email was received)"
    persona = spec["persona"].replace("{outbox}", last_email)
    sim = Simulator(persona, spec["opening"], client=client, model=args.sim_model)
    turns, error = [], None
    text, button = spec["opening"].strip(), None
    try:
        for _ in range(MAX_CUSTOMER_TURNS):
            t = agent.handle(text, button=button)
            turns.append({"customer": text, "button": button, "agent": t.reply, "options": t.options, "card": t.card,
                          "latency_ms": t.usage["latency_ms"], "cost_usd": t.usage["cost_usd"]})
            move = sim.respond(t)
            if move.done:
                break
            text, button = move.text, move.button
        else:
            error = f"turn_cap: {MAX_CUSTOMER_TURNS} customer turns without the simulator finishing"
    except SimulatorRefused as exc:
        error = f"simulator_refused: {exc}"
    except Exception as exc:  # recorded as a runner error, never as a pass or a fail
        error = f"{type(exc).__name__}: {exc}"[:500]
    trace = agent.session.trace
    jev_errors = [e["jev_error"] for e in trace if e["kind"] == "jev" and e.get("jev_error")]
    if jev_errors and not error:  # Jev was unavailable: the run does not measure what it is meant to
        error = f"jev_error: {jev_errors[0]}"
    snap = b.snapshot()
    delta = {"returns": snap["returns"][before[0]:], "tickets": snap["tickets"][before[1]:],
             "password_resets": snap["password_resets"][before[2]:]}
    result = None
    if not error:
        exp = render_expected(spec["expected"], store.policy)
        replies = [t["agent"] for t in turns]
        result = check_run(exp, delta, trace, replies)
        if "recommend" in exp:
            extra, notes = check_recommend(exp["recommend"], trace, replies, set(agent.toolbox.recommended_titles))
            result["checks"].update(extra)
            result["notes"] += notes
        if "return_contact" in exp:
            extra, notes = check_return_contact(exp["return_contact"], trace)
            result["checks"].update(extra)
            result["notes"] += notes
        result["passed"] = all(result["checks"].values())
    return {"opening": spec["opening"], "error": error, "result": result, "turns": turns, "trace": trace,
            "delta": delta, "system_text": system_text(agent), "agent_usage": agent.usage.as_dict(),
            "sim_cost_usd": round(sim.cost_usd, 5)}


def run_journey(journey: dict, run_index: int, args, client: anthropic.Anthropic, budget: Budget, jev: Jev) -> dict:
    if budget.exhausted():
        return {"journey": journey["id"], "run": run_index, "skipped": "budget"}
    store = Store.new(jev=jev, policy=Policy.load())
    steps, started = [], time.monotonic()
    for step in journey["steps"]:
        if "tick" in step:
            events = store.advance(step["tick"]["days"])
            steps.append({"tick": step["tick"], "today": store.backend.today.isoformat(), "events": events})
            continue
        s = run_session(step["session"], store, args, client)
        budget.add(s["agent_usage"]["cost_usd"] + s["sim_cost_usd"])
        steps.append({"session": s})
        if s["error"]:
            break
    sessions = [s["session"] for s in steps if "session" in s]
    error = next((s["error"] for s in sessions if s["error"]), None)
    snapshot, backend_snapshot = store.snapshot(), store.backend.snapshot()
    end = None if error else check_journey(journey["expected"], snapshot, backend_snapshot, [s["system_text"] for s in sessions])
    passed = not error and end["passed"] and all(s["result"]["passed"] for s in sessions)
    notes = [] if error else [f"session {i + 1}: {n}" for i, s in enumerate(sessions) for n in s["result"]["notes"]] + end["notes"]
    for s in sessions:
        s.pop("system_text")  # graded above; the transcript keeps the trace, not the whole prompt
    return {
        "journey": journey["id"], "title": journey["title"], "run": run_index, "error": error, "passed": passed,
        "notes": notes, "end_state": end, "steps": steps, "store": snapshot, "backend": backend_snapshot,
        "wrong_refunds": 0 if error else sum(s["result"]["wrong_refunds"] for s in sessions),
        "wall_s": round(time.monotonic() - started, 1),
    }


def summarize(journeys: list[dict], runs: list[dict], args, jev_spend: float) -> dict:
    by_id = defaultdict(list)
    for r in runs:
        if not r.get("skipped"):
            by_id[r["journey"]].append(r)
    rows, jev_latency, jev_calls = [], defaultdict(list), defaultdict(int)
    conversations = wrong = errors = 0
    agent_cost = sim_cost = 0.0
    for j in journeys:
        rs = by_id.get(j["id"], [])
        done = [r for r in rs if not r["error"]]
        errors += len(rs) - len(done)
        passes = sum(1 for r in done if r["passed"])
        for r in rs:
            for step in r["steps"]:
                if "session" not in step:
                    continue
                s = step["session"]
                conversations += 1
                agent_cost += s["agent_usage"]["cost_usd"]
                sim_cost += s["sim_cost_usd"]
                for e in s["trace"]:
                    if e["kind"] == "jev" and not e.get("jev_error"):
                        jev_calls[e["purpose"]] += 1
                        if e.get("latency_ms"):
                            jev_latency[e["purpose"]].append(e["latency_ms"])
        wrong += sum(r["wrong_refunds"] for r in done)
        rows.append({"id": j["id"], "title": j["title"], "runs": len(done), "passes": passes,
                     "pass_k": bool(done) and passes == len(done) == args.k, "errors": len(rs) - len(done),
                     "notes": sorted({n for r in done for n in r["notes"]}), "runner_errors": sorted({r["error"] for r in rs if r["error"]})})
    return {
        "config": {"model": args.model, "effort": args.effort, "sim_model": args.sim_model, "jev_model": config.JEV_MODEL,
                   "k": args.k, "label": args.label, "date": datetime.now().isoformat(timespec="seconds"),
                   "start_clock": config.TODAY.isoformat()},
        "headline": {"journeys": len(rows), "journeys_pass_k": sum(1 for r in rows if r["pass_k"]),
                     "conversations": conversations, "wrong_refunds": wrong, "runner_errors": errors},
        "jev": {"calls_by_purpose": dict(jev_calls),
                "latency_ms_p50_by_purpose": {k: int(statistics.median(v)) for k, v in jev_latency.items()},
                "spend_usd": round(jev_spend, 6)},
        "operations": {"agent_cost_total_usd": round(agent_cost, 4), "simulator_cost_usd": round(sim_cost, 4),
                       "agent_cost_per_conversation_usd": round(agent_cost / conversations, 4) if conversations else None},
        "journeys": rows,
    }


def write_report(out: Path, s: dict) -> None:
    c, h, j, o = s["config"], s["headline"], s["jev"], s["operations"]
    lines = [
        f"# Bookly journeys eval: {c['label']}", "",
        f"Agent `{c['model']}` (effort {c['effort']}), simulated customer `{c['sim_model']}`, decision model "
        f"`{c['jev_model']}`, k={c['k']}, clock starts {c['start_clock']}, run {c['date']}. Store on.", "",
        "## Headline",
        f"- **{h['journeys_pass_k']} of {h['journeys']} journeys pass all {c['k']} runs.**",
        f"- **{h['wrong_refunds']} wrong refunds in {h['conversations']} conversations.** Runner errors: {h['runner_errors']}.", "",
        "## Jev",
        "| Purpose | Calls | Latency p50 |", "|---|---|---|",
        *[f"| {p} | {n} | {j['latency_ms_p50_by_purpose'].get(p, '')} ms |" for p, n in sorted(j["calls_by_purpose"].items())],
        "", f"Jev spend for this run: ${j['spend_usd']:.6f}.", "",
        "## Cost of the conversations",
        f"- Agent ${o['agent_cost_total_usd']} (${o['agent_cost_per_conversation_usd']} per conversation); simulator ${o['simulator_cost_usd']}.", "",
        "## Journeys", "| ID | Journey | Passed | All runs | Notes |", "|---|---|---|---|---|",
    ]
    for r in s["journeys"]:
        notes = "; ".join(r["notes"] + [f"runner error: {e}" for e in r["runner_errors"]])[:300]
        lines.append(f"| {r['id']} | {r['title']} | {r['passes']}/{r['runs']}{' (+' + str(r['errors']) + ' err)' if r['errors'] else ''} "
                     f"| {'yes' if r['pass_k'] else 'NO'} | {notes} |")
    (out / "report.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--model", default=config.AGENT_MODEL)
    ap.add_argument("--effort", default=config.AGENT_EFFORT)
    ap.add_argument("--sim-model", default=config.SIM_MODEL)
    ap.add_argument("--only", default="")
    ap.add_argument("--budget", type=float, default=3.0, help="hard cap in USD on the Anthropic key for this run")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--label", default="journeys")
    args = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        ap.error("--label must be a plain name (letters, digits, - and _); it becomes a folder name")
    journeys = load_journeys({x.strip() for x in args.only.split(",") if x.strip()} or None)
    out = HERE / "results" / f"{datetime.now():%Y-%m-%d}-{args.label}"
    if out.exists():
        ap.error(f"{out} already exists; choose another --label so no saved run is overwritten")
    client = config.make_client(timeout=120, max_retries=3)
    budget, jev = Budget(args.budget), Jev()

    jobs = [(j, i) for j in journeys for i in range(args.k)]
    print(f"Running {len(jobs)} journey runs ({len(journeys)} journeys × k={args.k}) on {args.model} + {config.JEV_MODEL}; "
          f"Anthropic budget ${args.budget}, Jev budget ${config.JEV_BUDGET_USD} in total")
    runs = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_journey, j, i, args, client, budget, jev) for j, i in jobs]
        for f in as_completed(futures):
            r = f.result()
            runs.append(r)
            if r.get("skipped"):
                continue
            status = "ERR " if r["error"] else ("PASS" if r["passed"] else "FAIL")
            print(f"  {status} {r['journey']}#{r['run']} {r['wall_s']}s {(r['error'] or '; '.join(r['notes']))[:140]}")

    runs.sort(key=lambda r: (r["journey"], r["run"]))
    out.mkdir(parents=True)
    summary = summarize(journeys, runs, args, jev.spent_here)  # this run's own calls, not the shared log's total
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    with (out / "transcripts.jsonl").open("w") as fh:
        for r in runs:
            fh.write(json.dumps(r, default=str) + "\n")
    write_report(out, summary)
    if budget.stopped:
        print(f"\nSTOPPED EARLY: {budget.stopped}. These results are incomplete; do not report them.")
    h = summary["headline"]
    print(f"\n{h['journeys_pass_k']}/{h['journeys']} journeys pass all {args.k} runs; {h['wrong_refunds']} wrong refunds in "
          f"{h['conversations']} conversations; Anthropic ${budget.spent:.2f}, Jev ${summary['jev']['spend_usd']:.6f}. "
          f"Report: {out / 'report.md'}")


if __name__ == "__main__":
    main()
