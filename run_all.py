"""Run the whole milestone-1 audit end to end and write the reports.

    .venv/Scripts/python run_all.py [--months 24] [--seed 20261101] [--no-validate]

1. clean run:    generate (no plants) -> extract -> dbt build -> reports/clean-baseline.md
2. injected run: generate (plants)    -> extract -> dbt build -> score -> reports/recall.md

Both runs are written under data/generated/{clean,injected}/ (gitignored). The
two reports and the run manifest summary under reports/ are committed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from flow import audit, pipeline  # noqa: E402

REPORTS = ROOT / "reports"


def window_for(months: int) -> tuple[date, date]:
    end = date(2026, 10, 31)
    start = date(end.year, end.month, 1) - timedelta(days=31 * (months - 1))
    return date(start.year, start.month, 1), end


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "config" / "error_rates.yaml").read_text(encoding="utf-8"))
    seed = args.seed if args.seed is not None else cfg["seed_default"]
    months = args.months or cfg["scale"]["months"]
    window = window_for(months)
    REPORTS.mkdir(exist_ok=True)
    timings: dict[str, float] = {}
    summary: dict = {"seed": seed, "months": months, "window": [window[0].isoformat(), window[1].isoformat()]}

    for mode, inject in (("clean", False), ("injected", True)):
        out = ROOT / "data" / "generated" / mode
        t = time.time()
        m = pipeline.generate(seed=seed, window=window, out_dir=out, inject=inject, validate=not args.no_validate, config=cfg)
        timings[f"{mode}_generate_s"] = round(time.time() - t, 1)
        t = time.time()
        wh = pipeline.extract(out)
        timings[f"{mode}_extract_s"] = round(time.time() - t, 1)
        t = time.time()
        result = audit.run(wh, out / "audit.duckdb")
        timings[f"{mode}_audit_s"] = round(time.time() - t, 1)
        summary[mode] = {"counts": m["counts"], "validation": m["validation"], "flags": result.flags, "vocab_controls": result.vocab_controls}
        if mode == "clean":
            lines = ["# Clean-run baseline", "", "The injector planted nothing in this run. Every flag below is a false positive or a generator defect; zero is the target.", "", "| rule | flags |", "|---|---:|"]
            lines += [f"| {r} | {n} |" for r, n in result.flags.items()]
            lines += ["", "Vocabulary controls: " + ", ".join(f"{k}={v}" for k, v in result.vocab_controls.items()), "", f"Seed {seed}, window {window[0]} to {window[1]}, {m['counts']['performed']} performed exams."]
            (REPORTS / "clean-baseline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            t = time.time()
            report = audit.score(out / "audit.duckdb", out / "truth" / "planted_errors.csv", wh, REPORTS / "recall.md")
            timings["score_s"] = round(time.time() - t, 1)
            summary["recall"] = {k: {kk: vv for kk, vv in v.items() if kk != "variants"} for k, v in report["types"].items()}
            summary["recall_variants"] = {k: v["variants"] for k, v in report["types"].items()}
    summary["timings_s"] = timings
    (REPORTS / "run-summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"timings_s": timings, "clean_flags": summary["clean"]["flags"], "planted": summary["injected"]["counts"]["planted"]}, indent=1))
    print((REPORTS / "recall.md").read_text(encoding="utf-8")[:3000])


if __name__ == "__main__":
    main()
