"""Distil a Synthea run into the committed sample.

Reads synthea/output/csv/ and writes data/synthea-sample/:
  patients.csv           living residents only; direct identifiers dropped
  payer_transitions.csv  coverage periods, unchanged
  payers.csv             Id, NAME, OWNERSHIP (the generic payer names)
  MANIFEST.json          run parameters and the SHA-256 of each file

Also (re)writes tests/fixtures/synthea_default_name_hashes.json from the JAR's
own default payer file, so the default insurer names are stored only as
hashes and never appear in this repository in clear.

  .venv/Scripts/python synthea/distill.py --population 2000 --seed 20261101
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "synthea" / "output" / "csv"
SAMPLE = ROOT / "data" / "synthea-sample"
JAR = ROOT / "downloads" / "synthea" / "synthea-with-dependencies.jar"
FIXTURE = ROOT / "tests" / "fixtures" / "synthea_default_name_hashes.json"
SENTINEL = "Default Insurer Sentinel"

PATIENT_COLUMNS = ["Id", "BIRTHDATE", "DEATHDATE", "FIRST", "LAST", "GENDER", "CITY", "COUNTY", "ZIP"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--coverage-from", default="2024-01-01", help="keep coverage periods ending on or after this date")
    args = ap.parse_args()

    SAMPLE.mkdir(parents=True, exist_ok=True)
    with (OUT / "patients.csv").open(newline="", encoding="utf-8") as f:
        patients = [r for r in csv.DictReader(f) if r["DEATHDATE"] == ""]
    if len(patients) != args.population:
        raise SystemExit(f"expected {args.population} living residents, found {len(patients)}")
    alive = {p["Id"] for p in patients}
    write_csv(SAMPLE / "patients.csv", PATIENT_COLUMNS, patients)

    with (OUT / "payer_transitions.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        # Only the periods that can touch the study window: the generators
        # place exams from late 2024 onward, so older history is dead weight.
        coverage = [r for r in reader if r["PATIENT"] in alive and r["END_DATE"][:10] >= args.coverage_from]
    write_csv(SAMPLE / "payer_transitions.csv", header, coverage)

    with (OUT / "payers.csv").open(newline="", encoding="utf-8") as f:
        payers = list(csv.DictReader(f))
    write_csv(SAMPLE / "payers.csv", ["Id", "NAME", "OWNERSHIP"], payers)

    files = ["patients.csv", "payer_transitions.csv", "payers.csv"]
    manifest = {
        "synthea_version": "v4.0.0",
        "jar_sha256": sha256(JAR) if JAR.exists() else None,
        "population": args.population,
        "seed": args.seed,
        "age_range": "65-100",
        "state": "New Jersey",
        "properties": "config/synthea/synthea.properties",
        "living_residents": len(patients),
        "coverage_from": args.coverage_from,
        "coverage_rows": len(coverage),
        "sha256": {name: sha256(SAMPLE / name) for name in files},
    }
    (SAMPLE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if JAR.exists():
        jar = zipfile.ZipFile(JAR)
        rows = list(csv.DictReader(jar.read("payers/insurance_companies.csv").decode("utf-8-sig").splitlines()))
        default_private = [r["Name"] for r in rows if r["Ownership"].strip().lower() == "private"]
        hashes = sorted({hashlib.sha256(n.strip().lower().encode()).hexdigest() for n in default_private + [SENTINEL]})
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps({"note": "sha256 of lower-cased Synthea default private insurer names plus one sentinel; the names themselves are not stored", "sha256_lower": hashes}, indent=2) + "\n", encoding="utf-8")
        print(f"fixture: {len(hashes)} hashes")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
