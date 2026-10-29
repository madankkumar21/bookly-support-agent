"""Measure the intent router on the labelled set: every item k times, no agent and no backend involved.

    uv run python -m evals.router_eval --k 3
    uv run python -m evals.router_eval --k 3 --threshold 0.7 --label haiku-t07

Writes evals/results/<date>-router-<label>/: report.md, summary.json, runs.jsonl.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

from bookly import config
from bookly.agent import PRICES
from bookly.router import INTENTS, PROCEDURE_INTENTS, Router

HERE = Path(__file__).resolve().parent
THRESHOLDS = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9)
CONF_BUCKETS = ((0.0, 0.6), (0.6, 0.8), (0.8, 0.9), (0.9, 1.01))


def cost_of(model: str | None, usage) -> float:
    if usage is None or model not in PRICES:
        return 0.0
    pi, po, pr, pw = PRICES[model]
    cr = getattr(usage, "cache_read_input_tokens", 0) or 0
    cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return ((usage.input_tokens or 0) * pi + (usage.output_tokens or 0) * po + cr * pr + cw * pw) / 1_000_000


def needed(expected: list[str]) -> set[str]:
    """The procedures the turn needs. 'other' has no procedure, so nothing can be missing for it."""
    return {i for i in expected if i in PROCEDURE_INTENTS}


def score(run: dict, threshold: float) -> dict:
    """Judge one run at a given threshold."""
    fallback = bool(run["error"]) or not run["intents"] or run["confidence"] < threshold
    loaded = set(PROCEDURE_INTENTS) if fallback else {i for i in run["intents"] if i in PROCEDURE_INTENTS}
    need = needed(run["expected"])
    return {
        "needs": bool(need),  # runs that need no procedure ('other') are left out of the coverage count
        "fallback": fallback,
        "covered": need <= loaded,
        "missed_returns": "returns" in need and "returns" not in loaded,
        "over_loaded": not fallback and bool(loaded - need),
    }


def run_item(router: Router, item: dict, i: int) -> dict:
    r = router.classify(item["text"], item.get("prev", ""))
    if r.usage is not None and r.model not in PRICES:  # the agent refuses to misreport this; so does the eval
        r.error = r.error or f"unpriced model {r.model}"
    return {
        "id": item["id"], "kind": item["kind"], "run": i, "text": item["text"], "expected": item["expected"],
        "intents": r.intents, "confidence": r.confidence, "error": r.error, "model": r.model,
        "latency_ms": r.latency_ms, "cost_usd": round(cost_of(r.model, r.usage), 6),
        "exact": not r.error and set(r.intents) == set(item["expected"]),
    }


def pct(x: float | None) -> str:
    return "" if x is None else f"{x:.0%}"


def share(runs: list[dict], key: str) -> float | None:
    return round(sum(r[key] for r in runs) / len(runs), 3) if runs else None


def summarize(items: list[dict], runs: list[dict], args) -> dict:
    n = len(runs)
    at = [score(r, args.threshold) | r for r in runs]
    needing = [r for r in at if r["needs"]]
    lat = sorted(r["latency_ms"] for r in runs if not r["error"])
    by_item = defaultdict(list)
    for r in runs:
        by_item[r["id"]].append(r)
    consistent = sum(1 for rs in by_item.values() if len({tuple(sorted(r["intents"])) for r in rs}) == 1)

    recall = {}
    for intent in INTENTS:
        want = [r for r in runs if intent in r["expected"]]
        recall[intent] = {"runs": len(want), "recall": round(sum(intent in r["intents"] for r in want) / len(want), 3) if want else None}

    confusion = defaultdict(Counter)  # single-intent items: expected label -> predicted label set
    for r in runs:
        if len(r["expected"]) == 1:
            confusion[r["expected"][0]][",".join(sorted(r["intents"])) or "(error)"] += 1

    by_kind = {}
    for kind in sorted({it["kind"] for it in items}):
        rs = [r for r in at if r["kind"] == kind]
        by_kind[kind] = {"runs": len(rs), "exact": share(rs, "exact"), "covered": share([r for r in rs if r["needs"]], "covered")}

    buckets = []
    for lo, hi in CONF_BUCKETS:
        rs = [r for r in runs if not r["error"] and lo <= r["confidence"] < hi]
        buckets.append({"confidence": f"{lo:.1f}-{min(hi, 1.0):.1f}", "runs": len(rs),
                        "exact": round(sum(r["exact"] for r in rs) / len(rs), 3) if rs else None})

    sweep = []
    for t in THRESHOLDS:
        s = [score(r, t) for r in runs]
        sweep.append({"threshold": t, "covered": share([x for x in s if x["needs"]], "covered"),
                      "fallback": round(sum(x["fallback"] for x in s) / n, 3),
                      "missed_returns": sum(x["missed_returns"] for x in s)})

    misses = [{"id": r["id"], "run": r["run"], "text": r["text"], "expected": r["expected"], "intents": r["intents"],
               "confidence": r["confidence"], "error": r["error"]} for r in at if not r["covered"]]
    inexact = sorted({r["id"] for r in runs if not r["exact"]})

    return {
        "config": {"model": args.model, "k": args.k, "threshold": args.threshold, "items": len(items),
                   "date": datetime.now().isoformat(timespec="seconds"), "label": args.label,
                   "set": "evals/router_set.yaml (synthetic)"},
        "headline": {
            "classifications": n,
            "needing_a_procedure": len(needing),
            "exact_match": round(sum(r["exact"] for r in runs) / n, 3),
            "covered": share(needing, "covered"),
            "covered_count": sum(r["covered"] for r in needing),
            "missed_needed_procedure": sum(not r["covered"] for r in needing),
            "missed_returns": sum(r["missed_returns"] for r in at),
            "fallback_rate": round(sum(r["fallback"] for r in at) / n, 3),
            "over_loaded_rate": round(sum(r["over_loaded"] for r in at) / n, 3),
            "consistent_items": f"{consistent}/{len(by_item)}",
            "errors": sum(1 for r in runs if r["error"]),
        },
        "operations": {
            "latency_ms_p50": lat[len(lat) // 2] if lat else None,
            "latency_ms_p95": lat[int(len(lat) * 0.95) - 1] if lat else None,
            "cost_per_call_usd": round(statistics.mean(r["cost_usd"] for r in runs), 6),
            "cost_total_usd": round(sum(r["cost_usd"] for r in runs), 4),
        },
        "recall": recall, "by_kind": by_kind, "confidence_buckets": buckets, "threshold_sweep": sweep,
        "confusion_single_intent": {k: dict(v) for k, v in confusion.items()},
        "misses": misses, "inexact_items": inexact,
    }


def write_report(out: Path, s: dict) -> None:
    h, o, c = s["headline"], s["operations"], s["config"]
    lines = [
        f"# Intent router eval: {c['label']}", "",
        f"Model `{c['model']}`, k={c['k']}, threshold {c['threshold']}, {c['items']} items from {c['set']}, run {c['date']}.", "",
        "## Headline",
        f"- **Needed procedure loaded in {h['covered_count']} of the {h['needing_a_procedure']} classifications that needed one** "
        f"({h['missed_needed_procedure']} misses; {h['missed_returns']} missed the returns procedure; "
        f"{h['classifications'] - h['needing_a_procedure']} of {h['classifications']} needed none, because the message was out of scope).",
        f"- Exact label match {h['exact_match']:.0%}. Fallback to all procedures {h['fallback_rate']:.0%}. "
        f"Loaded more than needed {h['over_loaded_rate']:.0%}.",
        f"- Same answer on all {c['k']} runs: {h['consistent_items']} items. Router errors: {h['errors']}.",
        f"- Latency p50 {o['latency_ms_p50']} ms, p95 {o['latency_ms_p95']} ms. Cost ${o['cost_per_call_usd']:.6f} per call, "
        f"${o['cost_total_usd']:.4f} in total.", "",
        "## By kind", "| Kind | Runs | Exact | Needed procedure loaded |", "|---|---|---|---|",
        *[f"| {k} | {v['runs']} | {pct(v['exact'])} | {pct(v['covered']) or 'none needed'} |" for k, v in s["by_kind"].items()], "",
        "## Recall per intent", "| Intent | Runs that needed it | Recall |", "|---|---|---|",
        *[f"| {k} | {v['runs']} | {pct(v['recall'])} |" for k, v in s["recall"].items()], "",
        "## Threshold sweep (choose the threshold from this table)",
        "| Threshold | Needed procedure loaded | Fallback to all | Missed returns |", "|---|---|---|---|",
        *[f"| {t['threshold']} | {pct(t['covered'])} | {pct(t['fallback'])} | {t['missed_returns']} |" for t in s["threshold_sweep"]], "",
        "## Exact match by stated confidence", "| Confidence | Runs | Exact |", "|---|---|---|",
        *[f"| {b['confidence']} | {b['runs']} | {pct(b['exact'])} |" for b in s["confidence_buckets"]], "",
        "## Single-intent items: expected label → predicted labels",
        *[f"- **{k}**: " + ", ".join(f"{p} ×{n}" for p, n in sorted(v.items(), key=lambda x: -x[1]))
          for k, v in s["confusion_single_intent"].items()], "",
        "## Misses (a needed procedure was not loaded)",
        *([f"- {m['id']}#{m['run']}: \"{m['text']}\" expected {m['expected']}, got {m['intents']} "
           f"at {m['confidence']:.2f}{' (' + m['error'] + ')' if m['error'] else ''}" for m in s["misses"]] or ["- None."]), "",
        f"Items with any inexact run: {', '.join(s['inexact_items']) or 'none'}.",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")


def rescore(out: Path, args) -> None:
    """Recompute summary.json and report.md from saved runs, so a corrected metric never needs a new run."""
    runs = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines() if line.strip()]
    old = json.loads((out / "summary.json").read_text())["config"]
    args.model, args.k, args.threshold, args.label = old["model"], old["k"], old["threshold"], old["label"]
    items = list({r["id"]: {"id": r["id"], "kind": r["kind"]} for r in runs}.values())
    summary = summarize(items, runs, args)
    summary["config"]["date"] = old["date"]
    summary["config"]["rescored"] = datetime.now().isoformat(timespec="seconds")
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    write_report(out, summary)
    print(f"Re-graded {len(runs)} saved classifications. Report: {out / 'report.md'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--model", default=config.ROUTER_MODEL)
    ap.add_argument("--threshold", type=float, default=config.ROUTER_THRESHOLD)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--label", default="haiku")
    ap.add_argument("--rescore", help="re-grade a saved run folder from its runs.jsonl, with no API calls")
    args = ap.parse_args()
    if args.rescore:
        rescore(Path(args.rescore), args)
        return
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        ap.error("--label must be a plain name (letters, digits, - and _); it becomes a folder name")

    items = yaml.safe_load((HERE / "router_set.yaml").read_text())["items"]
    out = HERE / "results" / f"{datetime.now():%Y-%m-%d}-router-{args.label}"
    if out.exists():
        ap.error(f"{out} already exists; choose another --label so no saved run is overwritten")

    router = Router(client=config.make_client(timeout=30, max_retries=2), model=args.model, threshold=args.threshold)
    jobs = [(it, i) for it in items for i in range(args.k)]
    print(f"Classifying {len(jobs)} messages ({len(items)} items × k={args.k}) on {args.model}")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        runs = list(pool.map(lambda job: run_item(router, *job), jobs))
    runs.sort(key=lambda r: (r["id"], r["run"]))

    out.mkdir(parents=True)
    summary = summarize(items, runs, args)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    with (out / "runs.jsonl").open("w") as fh:
        for r in runs:
            fh.write(json.dumps(r) + "\n")
    write_report(out, summary)
    h = summary["headline"]
    print(f"\nNeeded procedure loaded {h['covered']:.0%}; exact {h['exact_match']:.0%}; fallback {h['fallback_rate']:.0%}; "
          f"missed returns {h['missed_returns']}; spend ${summary['operations']['cost_total_usd']:.4f}. Report: {out / 'report.md'}")


if __name__ == "__main__":
    main()
