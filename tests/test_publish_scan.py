"""The publish scan: nothing in the tracked files names the business this was
built for, carries a real NPI, a secret, or a local machine path. It runs with
a positive control: a planted line holding one of each must be flagged.
"""
import csv
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from flow import ids

ROOT = Path(__file__).resolve().parents[1]

# The NPIs this repository is allowed to contain: the synthetic ones in the
# vocabulary and the Synthea overrides, the CMS worked example, and the numbers
# `scripts/check_nppes.py` looked up and the registry did not know. The sample
# messages must draw from those, so they do not widen the list.
def _allowed_npis() -> set[str]:
    allowed = {"1234567893"}
    for p in [ROOT / "data" / "vocab" / "facilities.csv"]:
        with p.open(newline="", encoding="utf-8") as f:
            allowed |= {r["npi"] for r in csv.DictReader(f)}
    for p in (ROOT / "config" / "synthea" / "providers").glob("*.csv"):
        with p.open(newline="", encoding="utf-8") as f:
            allowed |= {r["npi"] for r in csv.DictReader(f)}
    check = ROOT / "data" / "vocab" / "nppes_check.json"
    if check.exists():
        allowed |= _registry_absent(json.loads(check.read_text(encoding="utf-8")))
    return allowed


def _registry_absent(check: dict) -> set[str]:
    """The registry check may not vouch for anything the registry knows: its
    `assigned` list must be empty, and only `absent` results carrying the
    synthetic `2` prefix count. A real NPI recorded there as assigned stays a
    hit (tests/test_publish_scan.py::test_control_the_registry_check_cannot_whitelist_an_assigned_npi)."""
    assert check.get("assigned") == [], f"the registry check found assigned NPIs: {check.get('assigned')}"
    return {n for n, r in check["results"].items() if r == "absent" and n.startswith("2")}


PATTERNS = {
    "business trace": re.compile(r"stat[ -]?imaging|getstatimaging", re.I),
    "secret shape": re.compile(r"postgres(ql)?://[^\s]+:[^\s]+@|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY"),
    "local path": re.compile(r"[A-Za-z]:\\Users\\|/Users/[a-z]|/home/[a-z]|\beromo\b", re.I),
}
NPI_SHAPE = re.compile(r"\b[12]\d{9}\b")
SKIP = {"tests/test_publish_scan.py"}
TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".csv", ".sql", ".txt", ".json", ".toml", ".sh", ".java", ".hl7", ".gitattributes", ".gitignore"}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    return [ROOT / f for f in out if f and f not in SKIP and (Path(f).suffix in TEXT_SUFFIXES or Path(f).name in TEXT_SUFFIXES)]


def scan(lines: list[tuple[str, int, str]], allowed_npis: set[str]) -> list[tuple[str, int, str, str]]:
    hits = []
    for path, no, line in lines:
        for label, rx in PATTERNS.items():
            if rx.search(line):
                hits.append((path, no, label, line.strip()[:120]))
        for cand in NPI_SHAPE.findall(line):
            if ids.is_valid_npi(cand) and cand not in allowed_npis:
                hits.append((path, no, "npi", cand))
    return hits


def _lines() -> list[tuple[str, int, str]]:
    out = []
    for p in tracked_files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            out.append((p.relative_to(ROOT).as_posix(), i, line))
    return out


def test_control_a_planted_line_of_each_kind_is_flagged():
    planted = [
        ("x.md", 1, "built for Stat Imaging"),
        ("x.md", 2, "DATABASE_URL=postgresql://user:pass@db.example.test/db"),
        ("x.md", 3, r"saved at C:\Users\someone\file"),
        ("x.md", 4, "NPI 2099999999 billed"),  # Luhn-valid, synthetic prefix, in no allow-list; checked absent in NPPES 2026-11-01
    ]
    labels = {h[2] for h in scan(planted, _allowed_npis())}
    assert labels == {"business trace", "secret shape", "local path", "npi"}


def _real_npi_from_nppes_file() -> str | None:
    """A real, assigned NPI from the registry's own data file, when NPPES_FILE
    names one (an npidata_pfile_*.csv, or the weekly zip that holds one;
    scripts/fetch_nppes_weekly.py fetches it when CMS's download site is up)."""
    path = os.environ.get("NPPES_FILE")
    if not path:
        return None
    p = Path(path)
    if p.suffix.lower() == ".zip":
        import io
        import zipfile
        with zipfile.ZipFile(p) as z:
            name = next(n for n in z.namelist() if n.startswith("npidata_pfile_") and n.endswith(".csv") and "fileheader" not in n.lower())
            with z.open(name) as f:
                for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace")):
                    if ids.is_valid_npi(row["NPI"]):
                        return row["NPI"]
        return None
    with p.open(newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if ids.is_valid_npi(row["NPI"]):
                return row["NPI"]
    return None


def _real_npi_from_registry_api() -> str | None:
    """A real, assigned NPI from the registry's public API at test time: the
    first organization the registry lists for one query. Nothing is stored."""
    import urllib.parse
    import urllib.request
    q = urllib.parse.urlencode({"version": "2.1", "enumeration_type": "NPI-2", "taxonomy_description": "General Acute Care Hospital", "state": "NJ", "limit": 1})
    req = urllib.request.Request(f"https://npiregistry.cms.hhs.gov/api/?{q}", headers={"User-Agent": "imaging-flow-audit publish-scan control"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    results = data.get("results") or []
    return results[0]["number"] if results else None


def test_control_a_real_npi_from_the_registry_is_flagged():
    """The scan must catch a REAL NPI, and a real NPI may never be committed here
    (EE, 2026-11-01: the first planted control turned out to be a named
    physician's). So the control is read from the registry at test time: from
    the NPPES data file if NPPES_FILE names one, otherwise from the registry
    API. In CI it must run; locally, no network means a skip, not a pass."""
    npi = _real_npi_from_nppes_file()
    source = "NPPES_FILE"
    if npi is None:
        source = "registry API"
        try:
            npi = _real_npi_from_registry_api()
        except Exception as e:  # offline, or the registry is down
            if os.environ.get("CI"):
                pytest.fail(f"the positive control against a real NPI could not run in CI: {e}")
            pytest.skip(f"no NPPES_FILE and the registry API is unreachable ({e}); the real-NPI control did not run")
    assert npi and ids.is_valid_npi(npi), (source, npi)
    hits = scan([("x.md", 1, f"NPI {npi} billed")], _allowed_npis())
    assert [h for h in hits if h[2] == "npi"] == [("x.md", 1, "npi", npi)], source


def test_control_the_registry_check_cannot_whitelist_an_assigned_npi():
    absent_only = {"assigned": [], "results": {"2012445096": "absent", "1234567893": "absent", "2099999990": "assigned"}}
    assert _registry_absent(absent_only) == {"2012445096"}  # a 1-prefix number and an assigned one do not count
    with pytest.raises(AssertionError):
        _registry_absent({"assigned": ["2099999990"], "results": {"2099999990": "assigned"}})


def test_control_the_scan_covers_the_whole_tree():
    files = tracked_files()
    assert len(files) > 60
    assert any(f.name == "README.md" for f in files) and any(f.suffix == ".py" for f in files)


def test_tracked_files_are_clean():
    hits = scan(_lines(), _allowed_npis())
    assert hits == [], hits[:20]
