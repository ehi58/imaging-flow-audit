"""Write the sample findings report from the latest run, marked SYNTHETIC.

    .venv/Scripts/python scripts/sample_findings_report.py [--pdf]

Reads reports/run-summary.json (the 24-month run) and writes
reports/sample-findings-report.html, and with --pdf prints it to
reports/sample-findings-report.pdf with headless Chrome or Edge. Every section
carries the word SYNTHETIC; the report describes planted errors in generated
data and nothing about any real provider.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "reports" / "run-summary.json"
OUT_HTML = ROOT / "reports" / "sample-findings-report.html"
OUT_PDF = ROOT / "reports" / "sample-findings-report.pdf"

FINDINGS = {
    "E01": ("Accession number on the image differs from the order", "Correct the header at the modality or re-associate the study in the PACS; add an accession check to the modality worklist step."),
    "E02": ("Laterality in the image header disagrees with the order", "Technologist confirms side at acquisition against the worklist; the LT/RT modifier on the claim follows the order, not the header."),
    "E03": ("Body part missing or not a defined term", "Map the protocol to a defined BodyPartExamined term at the modality; reject studies with an empty tag at import."),
    "E04": ("Image with no order", "Hold the claim until an order exists; review the stop's dispatch log for an unrecorded exam."),
    "E05": ("Member ID does not fit the payer's scheme or belongs to another resident", "Re-verify eligibility against the payer before the claim goes out; correct the registration record."),
    "E06": ("Coverage not in force on the date of service", "Run eligibility on the date of service; rebill to the payer in force, or to the resident, within timely filing."),
    "E07": ("Claim sent to the wrong payer", "Bill the primary payer in force on the date of service; for dual-eligibles, Medicare before Medicaid."),
    "E08": ("Ordering NPI missing or invalid", "Capture the orderer's individual NPI on every order; reject an order whose NPI fails the check digit or is an organization."),
    "E09": ("Report late, before the exam, or missing", "Route unread exams daily; no claim before a final report exists."),
    "E11": ("Views billed differ from views taken", "Code the exam from the study's instance count and the order, not from the schedule."),
    "E12": ("Transport line disagrees with the stop", "Bill transport from the dispatch log: one patient means R0070, more means R0075 with the count modifier; no transport on a day with no exam."),
}

COULD_NOT_CHECK = [
    "Part B claims during a Part A nursing-facility stay: the stay dates are carried in the data, but the code-level rule is not encoded until it is confirmed against CMS's consolidated billing update.",
    "FHIR validation against a server: the resources are built and shape-checked against the R4B models, but no FHIR server validated them in this milestone.",
    "Image content: the review reads headers only. Nothing judges an image.",
    "Payment amounts: the charges are a flat synthetic schedule, so no underpayment check runs here.",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true")
    args = ap.parse_args()
    s = json.loads(SUMMARY.read_text(encoding="utf-8"))
    counts = s["injected"]["counts"]
    flags = s["injected"]["flags"]
    recall = s["recall"]
    rows = []
    for rule, (title, fix) in FINDINGS.items():
        r = recall[rule]
        rows.append(
            f"<tr><td><b>{rule}</b></td><td>{html.escape(title)}</td><td>{flags[rule]}</td><td>{r['caught']} of {r['planted']}</td><td>{html.escape(fix)}</td></tr>"
        )
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Sample findings report (SYNTHETIC)</title>
<style>
 body {{ font-family: Georgia, 'Times New Roman', serif; margin: 2.2cm; color: #1a1a1a; line-height: 1.45; }}
 h1, h2 {{ font-family: Arial, Helvetica, sans-serif; }}
 .banner {{ border: 2px solid #1a1a1a; padding: .5em .8em; font-family: Arial, Helvetica, sans-serif; font-weight: bold; letter-spacing: .04em; margin-bottom: 1.4em; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 11pt; }}
 th, td {{ border: 1px solid #999; padding: .35em .5em; vertical-align: top; text-align: left; }}
 th {{ background: #eee; font-family: Arial, Helvetica, sans-serif; }}
 .small {{ font-size: 10pt; color: #444; }}
 @page {{ margin: 1.6cm; }}
</style></head><body>
<div class="banner">SYNTHETIC — a sample report built from generated data with planted errors. No real provider, patient or claim appears here.</div>
<h1>Sample findings report</h1>
<p class="small">Scope: a synthetic portable x-ray provider, {s['months']} months ({s['window'][0]} to {s['window'][1]}), {counts['patients']:,} residents, {counts['performed']:,} performed exams, {counts['claim_lines']:,} claim lines, {counts['planted']:,} planted errors. Seed {s['seed']}. Produced by the public repository's <code>run_all.py</code>.</p>

<h2>What was checked and what was found (SYNTHETIC)</h2>
<p>Each row is one check. "Flagged" is how many records the check flagged; "caught of planted" is how many of the errors deliberately planted in the data the check found. On real data the second column does not exist: it is the point of the synthetic run.</p>
<table>
<thead><tr><th>Check</th><th>Finding</th><th>Flagged</th><th>Caught of planted</th><th>The fix</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>

<h2>What could not be checked (SYNTHETIC)</h2>
<ul>{''.join(f'<li>{html.escape(x)}</li>' for x in COULD_NOT_CHECK)}</ul>

<h2>How to read a real report</h2>
<p>A real findings report lists each issue, the claims affected, the dollars at risk and the fix, and it says what could not be checked. The dollars column is absent here because the synthetic charges are a flat schedule and the point of this document is the method, not an amount.</p>
<p class="small">SYNTHETIC. Generated from the public repository's reports/run-summary.json. Nothing in this document is a result from a client.</p>
</body></html>
"""
    OUT_HTML.write_text(body, encoding="utf-8")
    print(f"wrote {OUT_HTML}")
    if args.pdf:
        chrome = next((p for p in [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", shutil.which("google-chrome"), shutil.which("chromium")] if p and Path(p).exists()), None)
        if not chrome:
            raise SystemExit("no Chrome or Edge found for --pdf")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", f"--print-to-pdf={OUT_PDF}", "--no-pdf-header-footer", OUT_HTML.resolve().as_uri()], check=True, capture_output=True)
        print(f"wrote {OUT_PDF}")


if __name__ == "__main__":
    main()
