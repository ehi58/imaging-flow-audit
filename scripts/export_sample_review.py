"""Export what a public sample-review page needs, as one JSON file.

    .venv/Scripts/python scripts/export_sample_review.py [--out reports/sample-review.json]

Contents: the flow steps; one sample message per HL7 step (v2.8 form) with the
fields the review reads marked; a DICOM header excerpt from one sample study;
each check in plain words with the error it catches and why it costs money;
the recall table from reports/run-summary.json (when a run has been made);
and the repository URL. Everything is synthetic, and the JSON says so.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flow import field_notes, modality  # noqa: E402
from flow.hl7_messages import FIELDS_USED  # noqa: E402

REPO_URL = "https://github.com/ehi58/imaging-flow-audit"

# The checks, in plain words. "costs" is why the error costs a provider money.
CHECKS = [
    {"id": "E01", "name": "The image carries a different accession number from the order", "catches": "A typo or a swapped study number between the order and the image.", "costs": "The claim cannot be tied to a valid order, so it is deniable on review."},
    {"id": "E02", "name": "The image's side disagrees with the order", "catches": "A left knee ordered, a right knee in the header, or no side at all.", "costs": "The LT/RT modifier on the claim no longer matches the record of what was done."},
    {"id": "E03", "name": "The body part is missing or not a defined term", "catches": "An empty or non-standard BodyPartExamined tag.", "costs": "The exam cannot be matched to its procedure code in a documentation review."},
    {"id": "E04", "name": "An image with no order", "catches": "A study that no order explains.", "costs": "Work that cannot be billed, or a billed exam with no order behind it."},
    {"id": "E05", "name": "The member ID is wrong", "catches": "A wrong payer prefix, a failed check digit, another patient's number.", "costs": "The payer rejects the claim."},
    {"id": "E06", "name": "Coverage was not in force on the date of service", "catches": "A claim sent to a plan whose period ended before, or started after, the exam.", "costs": "The payer denies it; the time to rebill is the cost."},
    {"id": "E07", "name": "The wrong payer", "catches": "Fee-for-service billed for an Advantage member; Medicaid billed first for a dual-eligible.", "costs": "A denial, and sometimes a timely-filing loss on the correct payer."},
    {"id": "E08", "name": "The ordering NPI is missing or invalid", "catches": "A blank, a failed check digit, an organization where an individual is required.", "costs": "Medicare requires a valid ordering practitioner on the claim."},
    {"id": "E09", "name": "The report is late, early or missing", "catches": "Turnaround past the service level, a report time before the exam, no report at all.", "costs": "An exam with no final report is not complete; a late one is a service failure."},
    {"id": "E11", "name": "Views billed differ from views taken", "catches": "A two-view code on a one-image study, or the reverse.", "costs": "Over-coding is an overpayment to return; under-coding is money left on the table."},
    {"id": "E12", "name": "The transport line disagrees with the stop", "catches": "A solo-trip fee at a shared stop, a shared-stop code for one patient, transport on a day with no exam.", "costs": "The transport fee is prorated by patients served; the wrong code pays the wrong amount."},
]

# Fields the review reads, per sample message: segment-field and what it is for.
HIGHLIGHTS = {
    "adt": [("PID-3", "the MRN the review joins everything on"), ("IN1-2", "the payer"), ("IN1-12", "coverage start"), ("IN1-13", "coverage end"), ("IN1-22", "primary or secondary"), ("IN1-36", "the member ID")],
    "order": [("ORC-1", "new or cancelled"), ("ORC-2", "placer order number, joined to the report"), ("OBR-4", "the procedure and its side"), ("OBR-31", "the statement of the patient's condition"), ("PRT-5", "the ordering NPI, matched to the claim"), ("IPC-1", "the accession, matched to the image and the claim")],
    "report": [("OBR-7", "when the exam was done"), ("OBR-22", "when the report was signed"), ("OBR-25", "final"), ("PRT-5", "the reading radiologist"), ("OBX-5", "the report body, always the synthetic template")],
}


def _field_table(segment_filter: set[str]) -> list[dict]:
    out = []
    for (version, seg, num), use in FIELDS_USED.items():
        if version == "2.8" and seg in segment_filter:
            out.append({"field": f"{seg}-{num}", "purpose": use.purpose})
    return out


def dicom_excerpt() -> list[dict]:
    """Header tags of one synthetic instance, written to a temp folder and read back."""
    import pydicom

    with tempfile.TemporaryDirectory() as tmp:
        from flow.orders import Exam

        exam = Exam(
            accession=field_notes.ORDER.accession, placer_order_number=field_notes.ORDER.placer_order_number, filler_order_number=field_notes.ORDER.filler_order_number,
            mrn=field_notes.PATIENT.mrn, trip_id="TRP0000001", facility_id="F01", order_datetime=field_notes.ORDER.order_datetime,
            scheduled_datetime=field_notes.ORDER.scheduled_datetime, exam_datetime=field_notes.REPORT.exam_datetime, cpt=field_notes.ORDER.cpt,
            description=field_notes.ORDER.description, body_part_examined="KNEE", laterality="L", views=3, ordering_npi=field_notes.ORDER.ordering_npi,
            ordering_family=field_notes.ORDER.ordering_family, ordering_given=field_notes.ORDER.ordering_given, reason=field_notes.ORDER.reason,
            study_instance_uid=field_notes.ORDER.study_instance_uid, control="NW",
        )
        paths = modality.write_study(field_notes.PATIENT, exam, Path(tmp), referring="BARLOW^BLAKE", rng=random.Random(1))
        ds = pydicom.dcmread(paths[0], stop_before_pixels=True)
        wanted = [
            ("0008,0050", "AccessionNumber", "matched to the order (E01, E04)"), ("0010,0020", "PatientID", "the MRN"), ("0010,0010", "PatientName", "must match registration"),
            ("0020,000D", "StudyInstanceUID", "the study's identity"), ("0008,0020", "StudyDate", "the date of service"), ("0008,0060", "Modality", "DX"),
            ("0018,0015", "BodyPartExamined", "must be a defined term (E03)"), ("0020,0060", "Laterality", "fallback side (E02)"), ("0020,0062", "ImageLaterality", "the side the review compares (E02)"),
            ("0018,5101", "ViewPosition", "one per instance; the count feeds E11"), ("0008,0090", "ReferringPhysicianName", "the orderer"), ("0008,0070", "Manufacturer", "SYNTHETIC"),
        ]
        rows = []
        for tag, keyword, why in wanted:
            value = str(ds.get(keyword, ""))
            rows.append({"tag": f"({tag})", "keyword": keyword, "value": value, "why": why})
        return rows


def recall_table() -> dict | None:
    p = ROOT / "reports" / "run-summary.json"
    if not p.exists():
        return None
    s = json.loads(p.read_text(encoding="utf-8"))
    rows = []
    for rule, r in s["recall"].items():
        rows.append({
            "rule": rule, "planted": r["planted"], "caught": r["caught"], "recall": round(r["recall"], 3),
            "interval_low": round(r["wilson_low"], 3), "interval_high": round(r["wilson_high"], 3),
            "holdout_planted": r["holdout_planted"], "holdout_caught": r["holdout_caught"],
            # Every flag the rule raised that was not a planted record of its own: on a
            # record the plant was expected to reach (cascade), on a record planted with
            # another error (cross), or on nothing anyone planted (unexplained; target 0).
            "flags_cascade": r["flags_cascade"], "flags_cross": r["flags_cross"], "flags_unexplained": r["flags_unexplained"],
        })
    return {
        "seed": s["seed"], "months": s["months"], "window": s["window"], "performed_exams": s["injected"]["counts"]["performed"],
        "planted": s["injected"]["counts"]["planted"], "cascade": s["injected"]["counts"].get("cascade", 0),
        "clean_flags": s["clean"]["flags"], "rows": rows,
        "label": "These numbers measure our checks on synthetic data with known planted errors. They are not results from a client.",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports" / "sample-review.json"))
    args = ap.parse_args()
    samples = field_notes.samples()
    pick = {
        "adt": "ADT^A04 (v2.8, structure ADT_A01)",
        "order": "OMI^O23 imaging order (v2.8)",
        "report": "ORU^R01 report (v2.8)",
    }
    out = {
        "synthetic": True,
        "note": "Everything here is synthetic: a fictitious resident and facility, synthetic NPIs absent from the NPI Registry, generic payers, a fixed report template. No patient data.",
        "repo": REPO_URL,
        "flow": [
            {"step": "Registration", "carries": "ADT^A04: who the resident is and what coverage they hold."},
            {"step": "Order", "carries": "OMI^O23 (v2.8) or ORM^O01 (v2.5.1): the exam, its side, the accession, the ordering practitioner and the reason."},
            {"step": "Image", "carries": "DICOM DX: the header repeats the accession, the patient, the body part and the side."},
            {"step": "Report", "carries": "ORU^R01: exam time, report time, final status, the reader."},
            {"step": "FHIR", "carries": "ServiceRequest, ImagingStudy and DiagnosticReport as R4 resources, sharing the accession."},
            {"step": "Claim", "carries": "Service lines: the exam's technical component, set-up, and the transport fee prorated by patients at the stop."},
        ],
        "samples": {k: {"title": v, "er7": samples[v][1].replace("\r", "\n").rstrip("\n"), "highlights": [{"field": f, "why": w} for f, w in HIGHLIGHTS[k]]} for k, v in pick.items()},
        "dicom_excerpt": dicom_excerpt(),
        "checks": CHECKS,
        "recall": recall_table(),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.out}; recall table: {'present' if out['recall'] else 'absent (run run_all.py first)'}")


if __name__ == "__main__":
    main()
