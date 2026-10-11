"""Run the scenario suite: every scenario k times against a fresh backend, a simulated customer, and the agent.

    uv run python -m evals.run_evals --k 5
    uv run python -m evals.run_evals --k 5 --override returns.print_return_window_days=14 --label window14
    uv run python -m evals.run_evals --k 1 --model claude-opus-5-5 --label opus
    uv run python -m evals.run_evals --only R1,R10 --k 2

Writes evals/results/<date>-<label>/: report.md, summary.json, transcripts.jsonl.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import anthropic
import yaml

from bookly import config
from bookly.agent import Agent
from bookly.backend import Backend
from bookly.policy import Policy
from evals.checks import check_run
from evals.simulator import Simulator, SimulatorRefused

HERE = Path(__file__).resolve().parent
MAX_CUSTOMER_TURNS = 10


def load_scenarios(only: set[str] | None) -> list[dict]:
    all_s = yaml.safe_load((HERE / "scenarios.yaml").read_text())["scenarios"]
    return [s for s in all_s if not only or s["id"] in only]


def expected_for(scenario: dict, overrides: dict) -> dict:
    exp = dict(scenario["expected"])
    for key, alt in (scenario.get("expected_overrides") or {}).items():
        k, v = key.split("=")
        if k in overrides and str(overrides[k]) == v:
            exp.update(alt)
    return exp


class Budget:
    def __init__(self, limit: float):
        self.limit, self.spent, self.lock = limit, 0.0, threading.Lock()

    def add(self, usd: float) -> None:
        with self.lock:
            self.spent += usd

    def exhausted(self) -> bool:
        with self.lock:
            return self.spent >= self.limit


def run_one(scenario: dict, run_index: int, args, overrides: dict, client: anthropic.Anthropic, budget: Budget) -> dict:
    if budget.exhausted():
        return {"scenario": scenario["id"], "run": run_index, "skipped": "budget"}
    policy = Policy.load(overrides=overrides)
    agent = Agent(backend=Backend.load(), policy=policy, client=client, model=args.model, effort=args.effort)
    sim = Simulator(scenario["persona"], scenario["opening"], client=client, model=args.sim_model)
    turns, error = [], None
    text, button = scenario["opening"].strip(), None
    started = time.monotonic()
    try:
        for _ in range(MAX_CUSTOMER_TURNS):
            t = agent.handle(text, button=button)
            turns.append({"customer": text, "button": button, "agent": t.reply, "options": t.options,
                          "card": t.card, "latency_ms": t.usage["latency_ms"], "cost_usd": t.usage["cost_usd"]})
            move = sim.respond(t)
            if move.done:
                break
            text, button = move.text, move.button
    except SimulatorRefused as exc:
        error = f"simulator_refused: {exc}"
    except Exception as exc:  # recorded as a runner error, never as a pass or a fail
        error = f"{type(exc).__name__}: {exc}"[:500]

    budget.add(agent.usage.cost_usd + sim.cost_usd)
    snapshot = agent.backend.snapshot()
    exp = expected_for(scenario, overrides)
    result = None if error else check_run(exp, snapshot, agent.session.trace, [t["agent"] for t in turns],
                                          clarify_first=scenario.get("clarify_first", False))
    return {
        "scenario": scenario["id"], "group": scenario["group"], "run": run_index, "error": error,
        "result": result, "turns": turns, "trace": agent.session.trace, "snapshot": snapshot,
        "agent_usage": agent.usage.as_dict(), "sim_cost_usd": round(sim.cost_usd, 5),
        "wall_s": round(time.monotonic() - started, 1),
    }


def wilson(passes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = passes / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, math.ceil(q * len(xs)) - 1))
    return xs[i]


def summarize(scenarios: list[dict], runs: list[dict], args, overrides: dict) -> dict:
    by_id: dict[str, list[dict]] = {}
    for r in runs:
        by_id.setdefault(r["scenario"], []).append(r)
    rows, all_turn_latency, costs, turns_count = [], [], [], []
    wrong_total = reason_mismatch_total = conversations = errors = 0
    resolvable_runs = resolved_runs = 0
    handoffs = complete_payloads = 0
    models = set()
    for s in scenarios:
        rs = [r for r in by_id.get(s["id"], []) if not r.get("skipped")]
        done = [r for r in rs if not r["error"]]
        errors += len(rs) - len(done)
        passes = sum(1 for r in done if r["result"]["passed"])
        failing = sorted({n for r in done for n in r["result"]["notes"]})
        for r in done:
            conversations += 1
            wrong_total += r["result"]["wrong_refunds"]
            reason_mismatch_total += r["result"]["reason_mismatch"]
            costs.append(r["agent_usage"]["cost_usd"])
            turns_count.append(len(r["turns"]))
            all_turn_latency += [t["latency_ms"] for t in r["turns"] if t["latency_ms"]]
            models.update(r["agent_usage"]["models_served"])
            if r["result"]["handoff"]:
                handoffs += 1
                complete_payloads += 1 if r["result"]["checks"].get("handoff_payload_complete") else 0
            if s.get("resolvable"):
                resolvable_runs += 1
                if r["result"]["checks"].get("end_state") and not r["result"]["handoff"] and r["result"]["passed"]:
                    resolved_runs += 1
        rows.append({
            "id": s["id"], "group": s["group"], "title": s["title"], "runs": len(done), "passes": passes,
            "pass_k": bool(done) and passes == len(done) == args.k, "errors": len(rs) - len(done), "notes": failing,
        })
    n_pass_k = sum(1 for r in rows if r["pass_k"])
    total_passes = sum(r["passes"] for r in rows)
    upper_wrong = 1 - 0.05 ** (1 / conversations) if conversations and wrong_total == 0 else None
    return {
        "config": {"model": args.model, "effort": args.effort, "sim_model": args.sim_model, "k": args.k,
                   "overrides": overrides, "date": datetime.now().isoformat(timespec="seconds"),
                   "policy_clock": config.TODAY.isoformat(), "label": args.label},
        "headline": {
            "scenarios": len(rows), "scenarios_pass_k": n_pass_k, "conversations": conversations,
            "wrong_refunds": wrong_total, "wrong_refund_upper_95": round(upper_wrong, 4) if upper_wrong is not None else None,
            "reason_mismatches": reason_mismatch_total,
            "run_pass_rate": round(total_passes / conversations, 4) if conversations else None,
            "run_pass_rate_wilson95": [round(x, 3) for x in wilson(total_passes, conversations)],
            "resolved_without_human": f"{resolved_runs}/{resolvable_runs}",
            "handoff_payload_complete": f"{complete_payloads}/{handoffs}",
            "runner_errors": errors,
        },
        "operations": {
            "median_customer_turns": statistics.median(turns_count) if turns_count else None,
            "turn_latency_ms_p50": pct(all_turn_latency, 0.5), "turn_latency_ms_p95": pct(all_turn_latency, 0.95),
            "agent_cost_per_conversation_usd": round(statistics.mean(costs), 4) if costs else None,
            "models_served": sorted(models),
            "simulator_cost_usd": round(sum(r.get("sim_cost_usd", 0) for r in runs), 4),
            "agent_cost_total_usd": round(sum(costs), 4),
        },
        "scenarios": rows,
    }


def business_case(summary: dict) -> dict:
    a = yaml.safe_load((HERE / "business_case.yaml").read_text())["assumed"]
    res_num, res_den = (int(x) for x in summary["headline"]["resolved_without_human"].split("/"))
    resolution = res_num / res_den if res_den else 0.0
    ai_cost = summary["operations"]["agent_cost_per_conversation_usd"] or 0.0
    contacts = a["contacts_per_month"] * a["share_status_and_returns"]
    saving = contacts * resolution * (a["cost_per_human_contact_usd"] - ai_cost)
    return {
        "measured": {"resolution_rate_on_synthetic_scenarios": round(resolution, 3), "ai_cost_per_conversation_usd": ai_cost},
        "assumed": a,
        "illustrative_monthly_saving_usd": round(saving, 0),
        "formula": "contacts/month × share(status+returns) × resolution rate × (human cost − AI cost per conversation)",
    }


def write_report(out: Path, summary: dict, bc: dict) -> None:
    h, o, c = summary["headline"], summary["operations"], summary["config"]
    lines = [
        f"# Bookly agent eval: {c['label']}",
        "",
        f"Model `{c['model']}` (effort {c['effort']}), simulated customer `{c['sim_model']}`, k={c['k']}, "
        f"policy overrides {c['overrides'] or 'none'}, clock {c['policy_clock']}, run {c['date']}.",
        "",
        "## Headline",
        f"- **{h['scenarios_pass_k']} of {h['scenarios']} scenarios pass all {c['k']} runs** (pass^{c['k']}).",
        f"- **{h['wrong_refunds']} wrong refunds in {h['conversations']} conversations**"
        + (f" (95% upper bound {h['wrong_refund_upper_95']:.1%})." if h["wrong_refund_upper_95"] is not None else "."),
        f"- Run pass rate {h['run_pass_rate']:.1%} (Wilson 95% {h['run_pass_rate_wilson95'][0]:.1%}–{h['run_pass_rate_wilson95'][1]:.1%})."
        if h["run_pass_rate"] is not None else "- No completed runs.",
        f"- Resolved without a human (resolvable scenarios): {h['resolved_without_human']} runs. "
        f"Handoff payloads complete: {h['handoff_payload_complete']}. Reason mismatches: {h['reason_mismatches']}. Runner errors: {h['runner_errors']}.",
        "",
        "## Operations",
        f"- Median customer turns {o['median_customer_turns']}; agent turn latency p50 {o['turn_latency_ms_p50']} ms, p95 {o['turn_latency_ms_p95']} ms.",
        f"- Agent cost per conversation ${o['agent_cost_per_conversation_usd']}; models served {', '.join(o['models_served'])}.",
        f"- Spend: agent ${o['agent_cost_total_usd']}, simulator ${o['simulator_cost_usd']}.",
        "",
        "## Scenarios",
        "| ID | Group | Scenario | Passed | pass^k | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for r in summary["scenarios"]:
        lines.append(f"| {r['id']} | {r['group']} | {r['title']} | {r['passes']}/{r['runs']}"
                     f"{' (+' + str(r['errors']) + ' err)' if r['errors'] else ''} | {'✅' if r['pass_k'] else '❌'} | {'; '.join(r['notes'])[:200]} |")
    lines += [
        "",
        "## Business case (illustrative, not a forecast)",
        f"- Formula: {bc['formula']}.",
        f"- Measured here: resolution rate on synthetic scenarios {bc['measured']['resolution_rate_on_synthetic_scenarios']:.0%} "
        f"(proves the method, not Bookly's number); AI cost per conversation ${bc['measured']['ai_cost_per_conversation_usd']}.",
        f"- Assumed (replace in discovery): {bc['assumed']['contacts_per_month']:,} contacts/month, "
        f"{bc['assumed']['share_status_and_returns']:.0%} status+returns, ${bc['assumed']['cost_per_human_contact_usd']:.2f} per human contact.",
        f"- Illustrative monthly saving: ${bc['illustrative_monthly_saving_usd']:,.0f}. Guardrail alongside it: {h['wrong_refunds']} wrong refunds.",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--model", default=config.AGENT_MODEL)
    ap.add_argument("--effort", default=config.AGENT_EFFORT)
    ap.add_argument("--sim-model", default=config.SIM_MODEL)
    ap.add_argument("--only", default="")
    ap.add_argument("--override", action="append", default=[], help="policy override, e.g. returns.print_return_window_days=14")
    ap.add_argument("--budget", type=float, default=35.0, help="hard cap in USD for this run")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--label", default="sonnet")
    args = ap.parse_args()

    overrides = dict(o.split("=", 1) for o in args.override)
    scenarios = load_scenarios({x.strip() for x in args.only.split(",") if x.strip()} or None)
    client = config.make_client(timeout=120, max_retries=3)
    budget = Budget(args.budget)
    out = HERE / "results" / f"{datetime.now():%Y-%m-%d}-{args.label}"
    out.mkdir(parents=True, exist_ok=True)

    jobs = [(s, i) for s in scenarios for i in range(args.k)]
    print(f"Running {len(jobs)} conversations ({len(scenarios)} scenarios × k={args.k}) on {args.model}; budget ${args.budget}")
    runs = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, s, i, args, overrides, client, budget) for s, i in jobs]
        for f in as_completed(futures):
            r = f.result()
            runs.append(r)
            if r.get("skipped"):
                continue
            status = "ERR " if r["error"] else ("PASS" if r["result"]["passed"] else "FAIL")
            note = r["error"] or "; ".join(r["result"]["notes"])
            print(f"  {status} {r['scenario']}#{r['run']} turns={len(r['turns'])} ${r['agent_usage']['cost_usd']:.3f} {note[:120]}")

    runs.sort(key=lambda r: (r["scenario"], r["run"]))
    summary = summarize(scenarios, runs, args, overrides)
    bc = business_case(summary)
    summary["business_case"] = bc
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    with (out / "transcripts.jsonl").open("w") as fh:
        for r in runs:
            fh.write(json.dumps(r, default=str) + "\n")
    write_report(out, summary, bc)
    h = summary["headline"]
    print(f"\n{h['scenarios_pass_k']}/{h['scenarios']} scenarios pass^{args.k}; {h['wrong_refunds']} wrong refunds in "
          f"{h['conversations']} conversations; spend ${budget.spent:.2f}. Report: {out / 'report.md'}")


if __name__ == "__main__":
    main()
