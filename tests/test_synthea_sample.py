"""The committed Synthea sample: shape, provenance, and no default insurer name.

Synthea's default payer file names real insurers and its default provider
files are real facilities. The committed sample is produced with generic
replacements for both, and this test scans it for the default insurer names.
The names themselves do not appear in this repository: the fixture holds
SHA-256 hashes of them (lower-cased), plus the hash of a sentinel string. The
sentinel is the positive control: a sample with the sentinel planted in it must
be flagged, or the scan cannot be trusted.
"""
import csv
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "synthea-sample"
FIXTURE = ROOT / "tests" / "fixtures" / "synthea_default_name_hashes.json"
SENTINEL = "Default Insurer Sentinel"


def _hash(name: str) -> str:
    return hashlib.sha256(name.strip().lower().encode()).hexdigest()


def _hits(lines, hashes: set[str]) -> list[str]:
    out = []
    for line in lines:
        for cell in line.split(","):
            if _hash(cell) in hashes:
                out.append(cell)
    return out


@pytest.fixture(scope="module")
def hashes() -> set[str]:
    return set(json.loads(FIXTURE.read_text())["sha256_lower"])


def test_fixture_holds_the_sentinel_and_six_insurer_hashes(hashes):
    assert _hash(SENTINEL) in hashes
    assert len(hashes) == 7


def test_sample_files_exist_with_the_expected_columns():
    patients = SAMPLE / "patients.csv"
    coverage = SAMPLE / "payer_transitions.csv"
    payers = SAMPLE / "payers.csv"
    for p in (patients, coverage, payers):
        assert p.exists(), p
    assert next(csv.reader(patients.open(newline="", encoding="utf-8"))) == [
        "Id", "BIRTHDATE", "DEATHDATE", "FIRST", "LAST", "GENDER", "CITY", "COUNTY", "ZIP",
    ]
    assert next(csv.reader(coverage.open(newline="", encoding="utf-8"))) == [
        "PATIENT", "MEMBERID", "START_DATE", "END_DATE", "PAYER", "SECONDARY_PAYER", "PLAN_OWNERSHIP", "OWNER_NAME",
    ]
    assert next(csv.reader(payers.open(newline="", encoding="utf-8"))) == ["Id", "NAME", "OWNERSHIP"]


def test_sample_carries_no_direct_identifier_columns():
    header = next(csv.reader((SAMPLE / "patients.csv").open(newline="", encoding="utf-8")))
    for banned in ("SSN", "DRIVERS", "PASSPORT", "ADDRESS", "LAT", "LON"):
        assert banned not in header


def test_sample_has_two_thousand_living_residents():
    rows = list(csv.DictReader((SAMPLE / "patients.csv").open(newline="", encoding="utf-8")))
    assert len(rows) == 2000
    assert all(r["DEATHDATE"] == "" for r in rows)


def test_sample_names_no_default_insurer(hashes):
    lines = []
    for p in SAMPLE.glob("*.csv"):
        lines.extend(p.read_text(encoding="utf-8").splitlines())
    assert _hits(lines, hashes) == []


def test_control_the_scan_flags_a_planted_sentinel(hashes):
    planted = [f"x,{SENTINEL},y"]
    assert _hits(planted, hashes) == [SENTINEL]


def test_manifest_records_the_run_and_the_file_hashes():
    manifest = json.loads((SAMPLE / "MANIFEST.json").read_text())
    assert manifest["synthea_version"] == "v4.0.0"
    assert manifest["seed"] == 20261101 and manifest["population"] == 2000
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((SAMPLE / name).read_bytes()).hexdigest() == digest


@pytest.mark.skipif(
    not (ROOT / "downloads" / "synthea" / "synthea-with-dependencies.jar").exists(),
    reason="LOCAL CONTROL ONLY: the Synthea jar is not present here; the sentinel control above still runs",
)
def test_control_the_jars_default_payer_file_is_flagged(hashes):
    import zipfile

    jar = zipfile.ZipFile(ROOT / "downloads" / "synthea" / "synthea-with-dependencies.jar")
    lines = jar.read("payers/insurance_companies.csv").decode("utf-8-sig").splitlines()
    assert len(_hits(lines, hashes)) == 6
