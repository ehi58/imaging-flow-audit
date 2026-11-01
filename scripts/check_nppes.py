"""Prove every synthetic NPI the repository carries is absent from NPPES.

Queries the NPI Registry API (v2.1) for each NPI in the vocabulary, the Synthea
provider overrides and the default-seed registry, and writes the answers with
the date to data/vocab/nppes_check.json. The positive control is an NPI the
registry is known to hold: it is looked up by organization name at run time
(so no real NPI is stored here) and must come back assigned, or the run fails.

    .venv/Scripts/python scripts/check_nppes.py
"""
from __future__ import annotations

import csv
import json
import random
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flow import registry  # noqa: E402
from flow.pipeline import REGISTRY_SIZE  # noqa: E402

API = "https://npiregistry.cms.hhs.gov/api/"
OUT = ROOT / "data" / "vocab" / "nppes_check.json"
CONTROL_ORG = ("MAYO CLINIC", "MN")


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({"version": "2.1", **params})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            # The registry throttles bursts; back off and try again.
            time.sleep(5 * (attempt + 1))
    raise SystemExit(f"NPPES unreachable: {url}")


def assigned(npi: str) -> bool:
    return int(_get({"number": npi}).get("result_count", 0)) > 0


def collect() -> set[str]:
    npis: set[str] = set()
    with (ROOT / "data" / "vocab" / "facilities.csv").open(newline="", encoding="utf-8") as f:
        npis |= {r["npi"] for r in csv.DictReader(f)}
    for p in (ROOT / "config" / "synthea" / "providers").glob("*.csv"):
        with p.open(newline="", encoding="utf-8") as f:
            npis |= {r["npi"] for r in csv.DictReader(f)}
    import yaml

    cfg = yaml.safe_load((ROOT / "config" / "error_rates.yaml").read_text(encoding="utf-8"))
    npis |= {p.npi for p in registry.build(random.Random(cfg["seed_default"]), **REGISTRY_SIZE)}
    return npis


def main() -> None:
    control = _get({"organization_name": CONTROL_ORG[0], "state": CONTROL_ORG[1], "limit": 1})
    if int(control.get("result_count", 0)) < 1:
        raise SystemExit("CONTROL FAILED: the registry returned no record for a known organization; the lookup cannot see NPPES")
    control_npi = str(control["results"][0]["number"])
    if not assigned(control_npi):
        raise SystemExit("CONTROL FAILED: a known-assigned NPI was reported absent")
    npis = sorted(collect())
    results = {}
    for n in npis:
        results[n] = "assigned" if assigned(n) else "absent"
        time.sleep(1.5)
    hits = [n for n, s in results.items() if s == "assigned"]
    OUT.write_text(json.dumps({"checked_on": date.today().isoformat(), "control": "a known organization's NPI was looked up by name and came back assigned", "count": len(results), "assigned": hits, "results": results}, indent=1) + "\n", encoding="utf-8")
    print(f"{len(results)} NPIs checked; assigned (must be none): {hits}")
    if hits:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
