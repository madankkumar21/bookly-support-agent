"""Measure the Jev judgments on their own: every labelled item k times, no agent and no conversation.

    uv run python -m evals.judgment_eval            # k=2, so each item also shows whether Jev repeats itself
    uv run python -m evals.judgment_eval --only remember --k 1 --label smoke
    uv run python -m evals.judgment_eval --engine haiku --label haiku   # the LLM baselines (evals/llm_judge.py):
    uv run python -m evals.judgment_eval --engine sonnet --label sonnet #   the same questions on Haiku or Sonnet

Each item is scored through the truth table in bookly/judgments.py, so the numbers describe outcomes (what
code would do), not raw probabilities. Writes evals/results/<date>-judgments-<label>/: report.md,
summary.json, runs.jsonl. The exact payload of every call is in logs/jev_calls.jsonl.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

from bookly import config, judgments
from bookly import recommend as recommender
from bookly.jev import Jev, JevError, spent_usd
from evals.llm_judge import HaikuJudge, JudgeError

HERE = Path(__file__).resolve().parent
KINDS = ("remember", "follow_up", "fit", "mood")


def score_remember(item: dict, probs: dict) -> dict:
    d = judgments.decide_remember(probs)
    want = {"likes": sorted(item["expect"].get("likes", [])), "dislikes": sorted(item["expect"].get("dislikes", []))}
    got = {"likes": sorted(d["likes"]), "dislikes": sorted(d["dislikes"])}
    saved_any = bool(got["likes"] or got["dislikes"])
    mood_ids = set(judgments.mood_questions())  # asked in the same request; scored by score_mood, not here
    shown = {k: round(v, 2) for k, v in probs.items()
             if k not in mood_ids and (k in ("lasting", "special_treatment") or v > judgments.NO)}
    return {"outcome": got, "correct": got == want, "wrong_direction": bool(item.get("must_save_nothing")) and saved_any,
            "unsettled": judgments.band(probs["lasting"]) == "unsettled", "shown": shown, "why": d["reason"]}


def score_follow_up(item: dict, probs: dict) -> dict:
    outcome = judgments.decide_follow_up(probs, asks_so_far=0)
    return {"outcome": outcome, "correct": outcome in item["expect"],
            "wrong_direction": outcome == "close" and "close" not in item["expect"],
            "unsettled": outcome == "ask", "shown": {k: round(v, 2) for k, v in probs.items()}, "why": ""}


def score_fit(item: dict, probs: dict) -> dict:
    p = next(iter(probs.values()))
    got = judgments.band(p)
    want = "yes" if item["expect"] in (True, "yes") else "no"
    return {"outcome": got, "correct": got == want, "wrong_direction": want == "no" and got == "yes",
            "unsettled": got == "unsettled", "shown": {"fit": round(p, 2)}, "why": ""}


def score_mood(item: dict, probs: dict) -> dict:
    """The message ends a conversation in which code recorded no action; the customer later comes back. The
    outcome is what the return table does then. As in contact.ended(), a message that says the problem is
    solved ends such a contact 'resolved'. (After a refusal the application does not read 'said solved'.)"""
    mood = judgments.decide_mood(probs.get("frustration"))
    gave_up, solved = judgments.band(probs["gave_up"]), judgments.band(probs["said_solved"])
    outcome = judgments.decide_return_contact("resolved" if solved == "yes" else "nothing_done", mood, gave_up)
    levels = probs.get("frustration") or []
    return {"outcome": outcome, "correct": outcome in item["expect"], "mood": mood, "mood_correct": mood == item["mood"],
            "wrong_direction": outcome == "early_escalation" and item["expect"] == ["none"],
            "unsettled": gave_up == "unsettled" or solved == "unsettled",
            "shown": {**{m: round(p, 2) for m, p in zip(judgments.MOODS, levels, strict=False)},
                      "gave_up": round(probs["gave_up"], 2), "said_solved": round(probs["said_solved"], 2)}, "why": f"mood {mood}"}


def request_for(kind: str, item: dict) -> tuple[dict, dict]:
    """(state, questions) exactly as the application builds them."""
    if kind in ("remember", "mood"):  # one request in the application: the mood questions ride with the tastes
        return judgments.remember_state(item["text"]), {**judgments.remember_questions(), **judgments.mood_questions()}
    if kind == "follow_up":
        return judgments.follow_up_state(item["subject"], item["messages"]), judgments.follow_up_questions(item["subject"])
    books = {b["title"]: b for b in recommender.catalog()}
    return (judgments.recommend_state([books[t] for t in item["purchased"]]),
            judgments.fit_questions([books[item["candidate"]]]))


SCORERS = {"remember": score_remember, "follow_up": score_follow_up, "fit": score_fit, "mood": score_mood}


def run_item(jev, kind: str, item: dict, i: int) -> dict:
    """jev is a bookly.jev.Jev or an evals.llm_judge.HaikuJudge: both take the same state and questions."""
    state, questions = request_for(kind, item)
    row = {"id": item["id"], "kind": kind, "run": i, "hard": bool(item.get("hard")),
           "held_out": bool(item.get("held_out")), "expect": item["expect"],
           "input": item.get("text") or item.get("messages") or f"{item['purchased']} -> {item['candidate']}"}
    try:
        answer = jev.ask(f"eval:{kind}", state, questions)
    except (JevError, JudgeError) as exc:
        return {**row, "error": str(exc)[:200]}
    extra = {"labels": answer.labels} if hasattr(answer, "labels") else {}
    probs = {**answer.probs, **getattr(answer, "scores", {})}  # a Score answer is its list of level probabilities
    return {**row, "error": None, "latency_ms": answer.latency_ms, "cost_usd": answer.cost_usd,
            "input_tokens": answer.input_tokens, **extra, **SCORERS[kind](item, probs)}


def summarize(runs: list[dict], args) -> dict:
    done = [r for r in runs if not r["error"]]
    by_kind = {}
    for kind in KINDS:
        rs = [r for r in done if r["kind"] == kind]
        if not rs:
            continue
        clear = [r for r in rs if not r["hard"]]
        by_item = defaultdict(list)
        for r in rs:
            by_item[r["id"]].append(json.dumps(r["outcome"], sort_keys=True))
        by_kind[kind] = {
            "runs": len(rs), "items": len(by_item),
            "outcome_accuracy": round(sum(r["correct"] for r in rs) / len(rs), 3),
            "outcome_accuracy_clear_items": round(sum(r["correct"] for r in clear) / len(clear), 3) if clear else None,
            "wrong_direction": sum(r["wrong_direction"] for r in rs),
            **({"mood_label_accuracy": round(sum(r["mood_correct"] for r in rs) / len(rs), 3)} if kind == "mood" else {}),
            "unsettled_rate": round(sum(r["unsettled"] for r in rs) / len(rs), 3),
            "same_outcome_every_run": f"{sum(1 for v in by_item.values() if len(set(v)) == 1)}/{len(by_item)}",
            "latency_ms_p50": int(statistics.median(r["latency_ms"] for r in rs)),
            "input_tokens_per_call": int(statistics.mean(r["input_tokens"] for r in rs)),
            "cost_per_call_usd": round(statistics.mean(r["cost_usd"] for r in rs), 8),
        }
    return {
        "config": {"model": getattr(args, "model_name", config.JEV_MODEL), "k": args.k, "label": args.label,
                   "date": datetime.now().isoformat(timespec="seconds"), "set": "evals/judgment_set.yaml (synthetic)",
                   "bands": {"yes": judgments.YES, "no": judgments.NO, "close_yes": judgments.CLOSE_YES}},
        "headline": {
            "runs": len(done), "errors": len(runs) - len(done),
            "outcome_accuracy": round(sum(r["correct"] for r in done) / len(done), 3) if done else None,
            "wrong_direction": sum(r["wrong_direction"] for r in done),
            "cost_total_usd": round(sum(r["cost_usd"] for r in done), 6),
            # Items added after a wording change and never used to word a question: the honest check of the change.
            "held_out_runs": sum(1 for r in done if r.get("held_out")),
            "held_out_correct": sum(1 for r in done if r.get("held_out") and r["correct"]),
        },
        "by_kind": by_kind,
        "misses": [{k: r[k] for k in ("id", "kind", "run", "hard", "input", "expect", "outcome", "shown", "wrong_direction", "why")}
                   for r in done if not r["correct"]],
    }


def write_report(out: Path, s: dict) -> None:
    c, h = s["config"], s["headline"]
    lines = [
        f"# Judgments eval: {c['label']}", "",
        f"Model `{c['model']}`, k={c['k']}, {c['set']}, bands yes ≥ {c['bands']['yes']}, no ≤ {c['bands']['no']}, "
        f"close ≥ {c['bands']['close_yes']}, run {c['date']}.", "",
        "## Headline",
        f"- **Outcome accuracy {h['outcome_accuracy']:.0%}** over {h['runs']} judged items "
        f"(each scored through its truth table). Errors: {h['errors']}.",
        f"- **Wrong-direction outcomes: {h['wrong_direction']}** (a taste saved from a special-treatment message, a "
        "follow-up closed without the customer saying it arrived, a clear non-fit rated yes, or a person brought in "
        "early for a calm customer).",
        *([f"- Mood label accuracy (calm / concerned / angry, before the table): {s['by_kind']['mood']['mood_label_accuracy']:.0%}."]
          if "mood" in s["by_kind"] else []),
        *([f"- Held-out items (added after a wording change, never used to word a question): "
           f"{h['held_out_correct']} of {h['held_out_runs']} correct."] if h.get("held_out_runs") else []),
        f"- Spend ${h['cost_total_usd']:.6f}.", "",
        "## By judgment",
        "| Judgment | Runs | Accuracy | Accuracy, clear items | Wrong direction | Unsettled | Same outcome every run | p50 | Tokens/call | Cost/call |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *[f"| {k} | {v['runs']} | {v['outcome_accuracy']:.0%} | "
          f"{'' if v['outcome_accuracy_clear_items'] is None else format(v['outcome_accuracy_clear_items'], '.0%')} | "
          f"{v['wrong_direction']} | {v['unsettled_rate']:.0%} | {v['same_outcome_every_run']} | {v['latency_ms_p50']} ms | "
          f"{v['input_tokens_per_call']} | ${v['cost_per_call_usd']:.6f} |" for k, v in s["by_kind"].items()], "",
        "## Misses (the outcome differed from the label)",
        *([f"- {m['id']}#{m['run']}{' (hard)' if m['hard'] else ''}{' **WRONG DIRECTION**' if m['wrong_direction'] else ''}: "
           f"{json.dumps(m['input'])[:160]} expected {json.dumps(m['expect'])}, got {json.dumps(m['outcome'])}; "
           f"answers {json.dumps(m['shown'])}{'; ' + m['why'] if m['why'] else ''}" for m in s["misses"]] or ["- None."]),
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--only", default="", help="comma list of: remember, follow_up, fit, mood")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--label", default="jev")
    ap.add_argument("--engine", choices=("jev", "haiku", "sonnet"), default="jev")
    args = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        ap.error("--label must be a plain name (letters, digits, - and _); it becomes a folder name")
    kinds = [k.strip() for k in args.only.split(",") if k.strip()] or list(KINDS)
    data = yaml.safe_load((HERE / "judgment_set.yaml").read_text())
    out = HERE / "results" / f"{datetime.now():%Y-%m-%d}-judgments-{args.label}"
    if out.exists():
        ap.error(f"{out} already exists; choose another --label so no saved run is overwritten")

    jev = Jev() if args.engine == "jev" else HaikuJudge(model=config.ROUTER_MODEL if args.engine == "haiku" else config.AGENT_MODEL)
    args.model_name = jev.model
    jobs = [(kind, item, i) for kind in kinds for item in data[kind] for i in range(args.k)]
    budget = (f"; ${spent_usd():.4f} of ${config.JEV_BUDGET_USD:.2f} Jev budget already spent"
              if args.engine == "jev" else "")
    print(f"Judging {len(jobs)} items ({', '.join(kinds)}; k={args.k}) on {jev.model}{budget}")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        runs = list(pool.map(lambda job: run_item(jev, *job), jobs))
    runs.sort(key=lambda r: (r["kind"], r["id"], r["run"]))

    out.mkdir(parents=True)
    summary = summarize(runs, args)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    with (out / "runs.jsonl").open("w") as fh:
        for r in runs:
            fh.write(json.dumps(r) + "\n")
    h = summary["headline"]
    if h["outcome_accuracy"] is not None:
        write_report(out, summary)
    if h["outcome_accuracy"] is None:
        print(f"\nNo item was judged ({h['errors']} errors). First error: {next(r['error'] for r in runs if r['error'])}")
        return
    print(f"\nOutcome accuracy {h['outcome_accuracy']:.0%}; wrong-direction outcomes {h['wrong_direction']}; "
          f"errors {h['errors']}; spend ${h['cost_total_usd']:.6f}. Report: {out / 'report.md'}")


if __name__ == "__main__":
    main()
