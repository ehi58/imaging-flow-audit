"""Fetch the current NPPES weekly dissemination file for the publish scan's
positive control.

    python scripts/fetch_nppes_weekly.py --out downloads/nppes

The scan must prove it can catch a real NPI (tests/test_publish_scan.py), and a
real NPI may not be committed to this repository. So the control reads one from
the registry's own file at test time: this script finds the current weekly
update on CMS's download page, downloads and unzips it, and writes the path of
the data CSV to <out>/NPPES_FILE. CI exports that path as NPPES_FILE. The file
is never committed (downloads/ is ignored).

Every failure exits non-zero: a control that cannot be built must say so, not
pass by absence.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

PAGE = "https://download.cms.gov/nppes/NPI_Files.html"
WEEKLY = re.compile(r"NPPES_Data_Dissemination_\d{6}_\d{6}_Weekly(?:_V2)?\.zip")


def _probe_recent_weekly() -> str | None:
    """The weekly file is named for the first and last day of its week
    (MMDDYY_MMDDYY). The week's start day has varied, so probe every start day
    over the last ten weeks, newest first, asking for one byte of each
    candidate (some hosts refuse HEAD)."""
    import datetime as dt
    today = dt.date.today()
    for back in range(0, 70):
        start = today - dt.timedelta(days=back)
        end = start + dt.timedelta(days=6)
        for suffix in ("", "_V2"):
            candidate = f"NPPES_Data_Dissemination_{start:%m%d%y}_{end:%m%d%y}_Weekly{suffix}.zip"
            req = urllib.request.Request(f"https://download.cms.gov/nppes/{candidate}", headers={"Range": "bytes=0-0", "User-Agent": "imaging-flow-audit publish-scan control"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    if r.status in (200, 206):
                        return candidate
            except Exception:
                continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="downloads/nppes")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    name = None
    try:
        with urllib.request.urlopen(PAGE, timeout=60) as r:
            html = r.read().decode("utf-8", errors="replace")
        names = sorted(set(WEEKLY.findall(html)))
        if names:
            name = names[-1]
    except Exception as e:  # the page is a stub without links some days; the names are regular
        print("download page unreadable:", e, file=sys.stderr)
    if name is None:
        name = _probe_recent_weekly()
    if name is None:
        print("no weekly file found on", PAGE, "or by probing the last ten weeks", file=sys.stderr)
        return 2
    url = f"https://download.cms.gov/nppes/{name}"
    zip_path = out / name
    if not zip_path.exists():
        print("downloading", url)
        urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        data = [n for n in z.namelist() if n.startswith("npidata_pfile_") and n.endswith(".csv") and "fileheader" not in n.lower()]
        if not data:
            print("no npidata_pfile_*.csv in", name, file=sys.stderr)
            return 3
        z.extract(data[0], out)
    csv_path = (out / data[0]).resolve()
    (out / "NPPES_FILE").write_text(str(csv_path), encoding="utf-8")
    print("NPPES_FILE", csv_path, f"({csv_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
