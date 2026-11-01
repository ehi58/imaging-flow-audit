"""Cascade truth.

A plant at the coverage grain (E05, E06), the claim grain (E07) or on another
exam's accession (E01 `other_same_day_accession`) changes more than the one
record the truth row names: every claim line of that patient and payer now
carries the bad member ID, every later claim falls outside the shortened
coverage, every line of the claim went to the wrong payer, the other exam now
holds an image it never took. A rule that fires on those records is right.

So the injector writes them too, as truth rows with `hop = cascade`, and the
scorer treats them as explained flags, never as planted errors: recall is
caught ÷ planted over the DIRECT rows, hold-outs apart, and every flag on the
injected run is a plant, a cross-flag on another plant, a cascade, or
UNEXPLAINED — and the last column must be zero, because an unexplained flag is
either a false positive or a mechanism nobody has written down.

Measured before this existed (24 months, seed 20261101): E05 flagged 1,134
rows no truth row named, E06 670, E07 197, E11 38. Every one of them was a
cascade of the four mechanisms above, and the report called them "flags
matching no plant".
"""
import csv
from datetime import date
from pathlib import Path

import pytest

from flow import audit, pipeline

WINDOW = (date(2025, 1, 1), date(2025, 2, 28))


def _rows(p: Path) -> list[dict]:
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("cascade")
    manifest = pipeline.generate(seed=77, window=WINDOW, out_dir=out, inject=True, validate=False)
    truth = _rows(out / "truth" / "planted_errors.csv")
    wh = pipeline.extract(out)
    audit.run(wh, out / "audit.duckdb")
    report = audit.score(out / "audit.duckdb", out / "truth" / "planted_errors.csv", wh, out / "recall.md")
    return out, manifest, truth, wh, report


def test_cascade_rows_are_marked_and_are_not_counted_as_planted(run):
    _, manifest, truth, _, _ = run
    direct = [t for t in truth if t["hop"] != "cascade"]
    cascade = [t for t in truth if t["hop"] == "cascade"]
    assert cascade, "coverage- and claim-grain plants must write cascade rows"
    assert manifest["counts"]["planted"] == len(direct)
    assert manifest["counts"]["cascade"] == len(cascade)
    # A cascade row carries the plant it belongs to, and no before/after of its own.
    assert all(t["error_id"] and t["variant"] and t["before"] == "" and t["after"] == "" for t in cascade)


def test_e05_cascade_covers_every_line_that_carries_the_planted_member_id(run):
    _, _, truth, wh, _ = run
    lines = _rows(wh / "claim_lines.csv")
    direct = [t for t in truth if t["error_id"] == "E05" and t["hop"] != "cascade"]
    assert direct
    keyed = {t["record_key"] for t in truth if t["error_id"] == "E05"}
    for t in direct:
        carriers = {l["claim_line_id"] for l in lines if l["member_id"] == t["after"] and l["payer_id"] != "SELF"}
        assert t["record_key"] in carriers
        assert carriers <= keyed, (t["variant"], sorted(carriers - keyed)[:5])


def test_e06_cascade_covers_the_patients_other_lines_with_that_payer(run):
    _, _, truth, wh, _ = run
    lines = _rows(wh / "claim_lines.csv")
    by_id = {l["claim_line_id"]: l for l in lines}
    direct = [t for t in truth if t["error_id"] == "E06" and t["hop"] != "cascade"]
    keyed = {t["record_key"] for t in truth if t["error_id"] == "E06"}
    assert direct
    for t in direct:
        tc = by_id[t["record_key"]]
        others = {l["claim_line_id"] for l in lines if l["mrn"] == tc["mrn"] and l["payer_id"] == tc["payer_id"]}
        assert others <= keyed, (t["variant"], sorted(others - keyed)[:5])


def test_e07_cascade_covers_the_other_lines_of_the_claim(run):
    _, _, truth, wh, _ = run
    lines = _rows(wh / "claim_lines.csv")
    by_id = {l["claim_line_id"]: l for l in lines}
    direct = [t for t in truth if t["error_id"] == "E07" and t["hop"] != "cascade"]
    keyed = {t["record_key"] for t in truth if t["error_id"] == "E07"}
    assert direct
    for t in direct:
        tc = by_id[t["record_key"]]
        same_claim = {l["claim_line_id"] for l in lines if l["claim_id"] == tc["claim_id"]}
        assert same_claim <= keyed, (sorted(same_claim - keyed)[:5])


def test_e01_same_day_accession_cascades_to_the_exam_that_gained_an_image(run):
    _, _, truth, wh, _ = run
    orders = {r["accession"] for r in _rows(wh / "orders.csv")}
    direct = [t for t in truth if t["error_id"] == "E01" and t["variant"] == "other_same_day_accession" and t["hop"] != "cascade"]
    assert direct
    cascade_acc = {t["record_key"] for t in truth if t["error_id"] == "E01" and t["hop"] == "cascade" and t["record_type"] == "accession"}
    for t in direct:
        if t["after"] in orders:  # a real exam gained the image (the fallback reversed-digit accession is nobody's)
            assert t["after"] in cascade_acc, t


def test_scorer_headline_is_core_only_and_every_flag_is_explained(run):
    out, _, truth, _, report = run
    for rule in audit.RULES:
        direct = [t for t in truth if t["error_id"] == rule and t["hop"] != "cascade"]
        core = [t for t in direct if t["holdout"] != "1"]
        hold = [t for t in direct if t["holdout"] == "1"]
        row = report["types"][rule]
        assert row["planted"] == len(core), rule
        assert row["holdout_planted"] == len(hold), rule
        assert 0 <= row["caught"] <= row["planted"] and 0 <= row["holdout_caught"] <= row["holdout_planted"]
        assert row["recall"] == pytest.approx(row["caught"] / row["planted"])
        assert row["flagged"] == row["caught"] + row["holdout_caught"] + row["flags_cascade"] + row["flags_cross"] + row["flags_unexplained"], rule
        assert row["flags_unexplained"] == 0, (rule, row)
    text = (out / "recall.md").read_text(encoding="utf-8")
    assert "cascade" in text and "unexplained" in text
    assert "| 0 |" in text  # at least one rule's unexplained column renders as zero
