"""The pipeline writes every artifact of the flow to disk from one seed, and the
extract step reads them back from the files (never from memory) into the
warehouse tables the audit queries.

Determinism: the same seed gives byte-identical artifacts (a SHA-256 manifest).
Validation: every HL7 file written is parsed by HAPI, and every v2.5.1 file by
hl7apy strict as well; the run fails otherwise.
"""
import csv
import json
import random
from datetime import date
from pathlib import Path

import pytest

from flow import pipeline, validate_hl7

WINDOW = (date(2025, 3, 3), date(2025, 3, 14))  # two weeks: a few hundred exams
HAVE_HAPI = validate_hl7.hapi_available()


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("run")
    manifest = pipeline.generate(seed=101, window=WINDOW, out_dir=out, inject=False, validate=HAVE_HAPI)
    return out, manifest


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_every_hop_leaves_its_files(run):
    out, m = run
    for rel in [
        "registry/providers.csv", "registration/patients.csv", "registration/coverage.csv",
        "dispatch/trips.csv", "dispatch/dispatch_log.csv", "orders/orders.csv", "reports/reports.csv",
        "claims/claim_lines.csv", "MANIFEST.json",
    ]:
        assert (out / rel).exists(), rel
    assert len(list((out / "hl7" / "adt" / "v2.8").glob("*.hl7"))) == m["counts"]["patients"]
    assert len(list((out / "hl7" / "adt" / "v2.5.1").glob("*.hl7"))) == m["counts"]["patients"]
    assert len(list((out / "hl7" / "orders" / "v2.8").glob("*.hl7"))) == m["counts"]["orders"]
    assert len(list((out / "hl7" / "reports" / "v2.8").glob("*.hl7"))) == m["counts"]["reports"]
    assert len(list((out / "dicom").glob("*/"))) == m["counts"]["studies"]
    assert len(list((out / "fhir").glob("*.json"))) == m["counts"]["reports"]
    assert m["counts"]["orders"] > 100 and m["counts"]["reports"] < m["counts"]["orders"]  # cancelled orders have no report


def test_the_manifest_hashes_every_file_and_a_second_run_matches(run, tmp_path):
    out, m = run
    assert m["seed"] == 101 and m["inject"] is False
    assert len(m["sha256"]) == m["files"] > 1000
    again = pipeline.generate(seed=101, window=WINDOW, out_dir=tmp_path / "again", inject=False, validate=False)
    assert again["sha256"] == m["sha256"]


def test_a_different_seed_gives_different_artifacts(run, tmp_path):
    _, m = run
    other = pipeline.generate(seed=102, window=WINDOW, out_dir=tmp_path / "other", inject=False, validate=False)
    assert other["sha256"] != m["sha256"]


@pytest.mark.skipif(not HAVE_HAPI, reason="HAPI jars or a JDK are missing")
def test_every_hl7_file_was_validated(run):
    _, m = run
    v = m["validation"]
    assert v["hapi"]["files"] == v["hl7_files"] and v["hapi"]["failed"] == 0
    assert v["hl7apy_strict"]["files"] > 0 and v["hl7apy_strict"]["failed"] == 0


def test_extract_reads_the_files_back_into_warehouse_tables(run):
    out, m = run
    wh = pipeline.extract(out)
    for name in ["patients", "coverage", "orders", "dispatch", "dicom_instances", "reports", "fhir_imagingstudy", "claim_lines", "providers"]:
        assert (wh / f"{name}.csv").exists(), name
    orders = _rows(wh / "orders.csv")
    assert len(orders) == m["counts"]["orders"]
    # The extract reads the HL7 files, so what it reports is what the message carried.
    o = orders[0]
    assert o["accession"].startswith("ACC") and o["ordering_npi"].isdigit() and o["cpt"].isdigit() and o["control"] in ("NW", "CA")
    cov = _rows(wh / "coverage.csv")
    assert {"mrn", "payer_id", "member_id", "priority", "start_date", "end_date"} <= set(cov[0])
    assert all(c["start_date"] <= c["end_date"] for c in cov)
    inst = _rows(wh / "dicom_instances.csv")
    assert len(inst) == m["counts"]["instances"]
    rep = _rows(wh / "reports.csv")
    assert len(rep) == m["counts"]["reports"] and all(r["status"] == "F" for r in rep)
    assert rep[0]["placer_order_number"].startswith("PLC") and rep[0]["report_datetime"] > rep[0]["exam_datetime"]


def test_extracted_orders_match_the_internal_table_in_the_clean_run(run):
    out, _ = run
    wh = pipeline.extract(out)
    internal = {r["accession"]: r for r in _rows(out / "orders" / "orders.csv")}
    for o in _rows(wh / "orders.csv"):
        i = internal[o["accession"]]
        assert o["mrn"] == i["mrn"] and o["cpt"] == i["cpt"] and o["ordering_npi"] == i["ordering_npi"] and o["laterality"] == i["laterality"]
