"""Re-grade saved transcripts with the current rubric. No model calls, no spend.

    uv run python -m evals.rescore evals/results/2026-10-13-opus-k5

Use it when a check itself was wrong: fix the check, add a test with the exact sentence,
then re-grade every saved run so all reports use the same rubric.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bookly.policy import Policy
from evals.checks import check_run
from evals.run_evals import business_case, expected_for, load_scenarios, render_expected, summarize, write_report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("result_dir")
    out = Path(ap.parse_args().result_dir)
    old = json.loads((out / "summary.json").read_text())
    cfg = old["config"]
    overrides = cfg.get("overrides") or {}
    policy = Policy.load(overrides=overrides)
    scenarios = load_scenarios({r["id"] for r in old["scenarios"]})
    by_id = {s["id"]: s for s in scenarios}

    runs, changed = [], 0
    for line in (out / "transcripts.jsonl").read_text().splitlines():
        r = json.loads(line)
        if not r.get("skipped") and not r.get("error"):
            s = by_id[r["scenario"]]
            exp = render_expected(expected_for(s, overrides), policy)
            new = check_run(exp, r["snapshot"], r["trace"], [t["agent"] for t in r["turns"]],
                            clarify_first=s.get("clarify_first", False))
            changed += new["passed"] != (r["result"] or {}).get("passed")
            r["result"] = new
        runs.append(r)

    args = argparse.Namespace(k=cfg["k"], model=cfg["model"], effort=cfg["effort"], sim_model=cfg["sim_model"], label=cfg["label"])
    summary = summarize(scenarios, runs, args, overrides)
    summary["config"]["date"] = cfg["date"]
    summary["config"]["rescored"] = True
    summary["business_case"] = business_case(summary)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    with (out / "transcripts.jsonl").open("w") as fh:
        for r in runs:
            fh.write(json.dumps(r, default=str) + "\n")
    write_report(out, summary, summary["business_case"])
    h = summary["headline"]
    print(f"{out.name}: {changed} run verdict(s) changed; now {h['scenarios_pass_k']}/{h['scenarios']} pass^{cfg['k']}, "
          f"{h['wrong_refunds']} wrong refunds in {h['conversations']}")


if __name__ == "__main__":
    main()
