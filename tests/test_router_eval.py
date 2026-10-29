"""The router eval's scoring: every number in docs/ROUTER.md comes from these functions, so they get tests too."""

from types import SimpleNamespace as NS

from bookly.router import PROCEDURE_INTENTS
from evals.router_eval import score, summarize


def run(rid, kind, expected, intents, confidence=0.95, error=None):
    return {"id": rid, "kind": kind, "run": 0, "text": rid, "expected": expected, "intents": intents,
            "confidence": confidence, "error": error, "model": "claude-haiku-5-5", "latency_ms": 1000,
            "cost_usd": 0.0001, "exact": not error and set(intents) == set(expected)}


RUNS = [
    run("A", "single", ["returns"], ["policy"]),                     # a miss of the returns procedure
    run("B", "vague", ["returns"], ["returns", "order_status"]),     # wider than needed
    run("C", "single", ["policy"], ["order_status"], confidence=0.4),  # wrong, but below the bar: falls back
    run("D", "out_of_scope", ["other"], ["other"]),                  # needs no procedure
]


def test_score_judges_each_case():
    a, b, c, d = (score(r, 0.6) for r in RUNS)
    assert not a["covered"] and a["missed_returns"] and not a["fallback"]
    assert b["covered"] and b["over_loaded"] and not b["missed_returns"]
    assert c["fallback"] and c["covered"] and not c["over_loaded"]  # every procedure loads
    assert d["covered"] and not d["needs"]


def test_summary_counts_coverage_only_over_runs_that_need_a_procedure():
    items = [{"id": r["id"], "kind": r["kind"]} for r in RUNS]
    s = summarize(items, RUNS, NS(model="claude-haiku-5-5", k=1, threshold=0.6, label="t"))
    h = s["headline"]
    assert h["needing_a_procedure"] == 3 and h["covered_count"] == 2 and h["missed_needed_procedure"] == 1
    assert h["missed_returns"] == 1 and h["fallback_rate"] == 0.25 and h["exact_match"] == 0.25
    assert s["by_kind"]["out_of_scope"]["covered"] is None  # nothing was needed, so nothing to count
    assert [m["id"] for m in s["misses"]] == ["A"]


def test_threshold_sweep_trades_misses_for_fallback():
    items = [{"id": r["id"], "kind": r["kind"]} for r in RUNS]
    sweep = {t["threshold"]: t for t in summarize(items, RUNS, NS(model="m", k=1, threshold=0.6, label="t"))["threshold_sweep"]}
    assert sweep[0.0]["fallback"] == 0 and sweep[0.0]["covered"] == round(1 / 3, 3)  # C's wrong label now counts
    assert sweep[0.9]["fallback"] == 0.25  # only C is below 0.9 and falls back
    assert set(PROCEDURE_INTENTS) == {"order_status", "returns", "policy"}


def test_an_error_falls_back_and_is_never_exact():
    r = run("E", "single", ["returns"], [], confidence=0.0, error="unpriced model x")
    assert score(r, 0.6)["fallback"] and score(r, 0.6)["covered"] and not r["exact"]
