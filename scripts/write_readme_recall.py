"""Fill the README's recall section from the last run's reports.

Reads reports/recall.md and reports/run-summary.json (written by run_all.py)
and replaces everything between the RECALL TABLE markers in README.md. The
numbers are copied, never retyped: the per-rule table is the one the scorer
wrote. Run after `python run_all.py --months 24`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- RECALL TABLE -->"
END = "<!-- /RECALL TABLE -->"


def per_rule_table(recall_md: str) -> str:
    lines = recall_md.splitlines()
    head = next(i for i, l in enumerate(lines) if l.startswith("| rule | planted |"))
    end = head
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return "\n".join(lines[head:end])


def holdout_misses(recall_md: str) -> list[tuple[str, str, int, int]]:
    out = []
    for l in recall_md.splitlines():
        m = re.match(r"\| (E\d\d) \| ([a-z0-9_]+) \| yes \| (\d+) \| (\d+) \|", l)
        if m and int(m.group(4)) < int(m.group(3)):
            out.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4))))
    return out


def main() -> None:
    recall_md = (ROOT / "reports" / "recall.md").read_text(encoding="utf-8")
    summary = json.loads((ROOT / "reports" / "run-summary.json").read_text(encoding="utf-8"))
    inj = summary["injected"]["counts"]
    clean_total = sum(summary["clean"]["flags"].values())
    unexplained = sum(r["flags_unexplained"] for r in summary["recall"].values())
    misses = holdout_misses(recall_md)
    miss_lines = "\n".join(
        f"- **{rule} `{variant}`** (hold-out): {caught} of {planted} caught. The rule does not see this way of making the error; "
        f"that is what the hold-out is for, and it stays in the table rather than being fixed into the rule after the fact."
        for rule, variant, planted, caught in misses
    ) or "- Every hold-out variant was caught at least as often as its core variants."
    body = f"""{START}

Measured on seed {summary['seed']}, {summary['months']} months ({summary['window'][0]} to {summary['window'][1]}):
{inj['performed']:,} performed exams, {inj['planted']:,} planted errors, {inj.get('cascade', 0):,} cascade records.
**These numbers measure the rules on synthetic data with known planted errors. They are not results from any client.**

{per_rule_table(recall_md)}

Recall is caught ÷ planted over the core variants of each rule, with a 95% Wilson interval. Hold-out variants
were written after the rules were frozen and are scored apart. A **cascade flag** is on a record the plant was
expected to reach without being the planted record (the patient's other claim lines after a coverage or member-ID
change, the other lines of a claim sent to the wrong payer, the exam that gained an image); a **cross-flag** is on a
record planted with a different error; an **unexplained flag** is a false positive or a mechanism nobody has
written down. Unexplained flags in this run: **{unexplained}**. The clean run, with nothing planted, raised
**{clean_total}** flags (`reports/clean-baseline.md`).

{miss_lines}

Per-variant numbers: `reports/recall.md`. How each error is planted and what it costs: `docs/error-catalog.md`.

{END}"""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if END in readme:
        pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
        assert pattern.search(readme)
        readme = pattern.sub(lambda _: body, readme, count=1)
    else:
        assert readme.count(START) == 1, "README needs exactly one RECALL TABLE marker"
        readme = readme.replace(START, body, 1)
    (ROOT / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    print(f"README recall section written: {len(summary['recall'])} rules, {unexplained} unexplained, {len(misses)} hold-out miss(es)")


if __name__ == "__main__":
    main()
