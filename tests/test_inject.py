"""The injector plants each error at its hop, writes the truth, and the written
artifacts carry the planted value (so the audit, which reads files, can see it).

Every error id and every variant, hold-out included, must occur at least once
in a two-month window, and the clean seed plants nothing.
"""
import csv
import json
import random
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
import yaml

from flow import pipeline

WINDOW = (date(2025, 1, 1), date(2025, 2, 28))
CONFIG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "error_rates.yaml").read_text())


@pytest.fixture(scope="module")
def injected(tmp_path_factory):
    out = tmp_path_factory.mktemp("inj")
    manifest = pipeline.generate(seed=77, window=WINDOW, out_dir=out, inject=True, validate=False)
    truth = list(csv.DictReader((out / "truth" / "planted_errors.csv").open(newline="", encoding="utf-8")))
    return out, manifest, truth


def test_clean_run_plants_nothing(tmp_path):
    m = pipeline.generate(seed=77, window=(date(2025, 1, 1), date(2025, 1, 14)), out_dir=tmp_path, inject=False, validate=False)
    assert m["counts"]["planted"] == 0 and not (tmp_path / "truth").exists()


def test_every_error_type_and_every_variant_is_planted(injected):
    _, _, truth = injected
    seen = Counter((t["error_id"], t["variant"]) for t in truth)
    for eid, spec in CONFIG["errors"].items():
        for variant in spec["variants"] + [spec["holdout"]]:
            assert seen[(eid, variant)] >= 1, (eid, variant)
    assert all((t["holdout"] == "1") == (t["variant"] == CONFIG["errors"][t["error_id"]]["holdout"]) for t in truth)


def test_realised_rates_are_near_the_configured_rates(injected):
    _, m, truth = injected
    by_type = Counter(t["error_id"] for t in truth if t["hop"] != "cascade")  # cascades are consequences, not plants
    performed = m["counts"]["performed"]
    for eid, spec in CONFIG["errors"].items():
        expected = spec["rate"] * performed
        assert 0.4 * expected <= by_type[eid] <= 2.0 * expected + 3, (eid, by_type[eid], expected)


def test_truth_rows_name_a_real_record_and_the_change(injected):
    _, _, truth = injected
    for t in truth:
        assert t["record_type"] in ("accession", "study_uid", "claim_line_id", "coverage_id", "trip_id")
        assert t["record_key"] and t["hop"] in ("registration", "order", "image", "report", "claim", "cascade") and t["field"]
        if t["hop"] == "cascade":
            assert t["before"] == "" and t["after"] == "", t  # the change is on the plant's own row (tests/test_cascade_truth.py)
        else:
            assert t["before"] != t["after"], t


def _rows(p: Path) -> list[dict]:
    return list(csv.DictReader(p.open(newline="", encoding="utf-8")))


def test_image_hop_plants_are_in_the_dicom_headers_not_in_the_orders(injected):
    out, _, truth = injected
    wh = pipeline.extract(out)
    inst = {r["study_folder"]: r for r in _rows(wh / "dicom_instances.csv")}
    orders = {r["accession"]: r for r in _rows(wh / "orders.csv")}
    e01 = [t for t in truth if t["error_id"] == "E01" and t["hop"] != "cascade"]
    assert e01
    for t in e01:
        header = inst[t["record_key"]]
        assert header["accession"] == t["after"] and header["accession"] != t["record_key"]
        assert orders[t["record_key"]]["accession"] == t["record_key"]  # the order itself is untouched
    for t in (x for x in truth if x["error_id"] == "E03" and x["variant"] == "tag_absent"):
        assert inst[t["record_key"]]["body_part_tag_present"] == "0"
    for t in (x for x in truth if x["error_id"] == "E02" and x["variant"] == "lr_swapped"):
        assert inst[t["record_key"]]["image_laterality"] == t["after"] and orders[t["record_key"]]["laterality"] == t["before"]


def test_order_hop_plants_reach_both_the_message_and_the_claim(injected):
    out, _, truth = injected
    wh = pipeline.extract(out)
    orders = {r["accession"]: r for r in _rows(wh / "orders.csv")}
    claims = _rows(wh / "claim_lines.csv")
    for t in (x for x in truth if x["error_id"] == "E08"):
        assert orders[t["record_key"]]["ordering_npi"] == t["after"]
        tc = [c for c in claims if c["accession"] == t["record_key"] and c["hcpcs"] != "Q0092"]
        assert tc and tc[0]["ordering_npi"] == t["after"]


def test_report_hop_plants(injected):
    out, _, truth = injected
    wh = pipeline.extract(out)
    orders = {r["accession"]: r for r in _rows(wh / "orders.csv")}
    reports = {r["placer_order_number"]: r for r in _rows(wh / "reports.csv")}
    for t in (x for x in truth if x["error_id"] == "E09"):
        placer = orders[t["record_key"]]["placer_order_number"]
        if t["variant"] == "no_report":
            assert placer not in reports
        elif t["variant"] == "report_before_exam":
            assert reports[placer]["report_datetime"] < reports[placer]["exam_datetime"]
        else:
            assert reports[placer]["report_datetime"] == t["after"]


def test_claim_hop_plants(injected):
    out, _, truth = injected
    wh = pipeline.extract(out)
    lines = {r["claim_line_id"]: r for r in _rows(wh / "claim_lines.csv")}
    for t in (x for x in truth if x["record_type"] == "claim_line_id" and x["error_id"] in ("E05", "E07", "E11", "E12") and x["hop"] != "cascade"):
        line = lines[t["record_key"]]
        if t["field"] == "hcpcs" and " " in t["after"]:
            assert f"{line['hcpcs']} {line['modifiers']}" == t["after"], (t, line)
        elif t["field"] == "date_of_service":
            assert line["date_of_service"] == t["after"]
        else:
            assert line[t["field"]] == t["after"], (t, line[t["field"]])


def test_e06_plants_leave_the_billed_date_outside_every_period_of_that_payer(injected):
    out, _, truth = injected
    wh = pipeline.extract(out)
    lines = {r["claim_line_id"]: r for r in _rows(wh / "claim_lines.csv")}
    cov = _rows(wh / "coverage.csv")
    e06 = [t for t in truth if t["error_id"] == "E06" and t["hop"] != "cascade"]
    assert e06
    for t in e06:
        line = lines[t["record_key"]]
        periods = [c for c in cov if c["mrn"] == line["mrn"] and c["payer_id"] == line["payer_id"]]
        assert periods, "the payer still appears in the ADT coverage"
        assert not any(c["start_date"] <= line["date_of_service"] <= c["end_date"] for c in periods), (t, line["date_of_service"], periods)


def test_coverage_hop_plants_are_in_the_adt_messages(injected):
    out, _, truth = injected
    wh = pipeline.extract(out)
    cov = _rows(wh / "coverage.csv")
    internal = {r["coverage_id"]: r for r in _rows(out / "registration" / "coverage.csv")}
    for t in (x for x in truth if x["record_type"] == "coverage_id"):
        row = internal[t["record_key"]]
        assert row[t["field"]] == t["after"]
        # The ADT the review reads carries the same (planted) value.
        match = [c for c in cov if c["mrn"] == row["mrn"] and c["payer_id"] == row["payer_id"] and c["start_date"] == row["start_date"]]
        assert match and match[0]["end_date"] == row["end_date"]


def test_injection_is_deterministic(tmp_path):
    a = pipeline.generate(seed=78, window=(date(2025, 1, 1), date(2025, 1, 21)), out_dir=tmp_path / "a", inject=True, validate=False)
    b = pipeline.generate(seed=78, window=(date(2025, 1, 1), date(2025, 1, 21)), out_dir=tmp_path / "b", inject=True, validate=False)
    assert a["sha256"] == b["sha256"] and a["counts"]["planted"] > 0
