"""Read the written artifacts back into the warehouse tables the audit queries.

This is the review's own extract step, and it reads FILES, never the
generator's memory: the HL7 messages (parsed with python-hl7, which is
version-agnostic and positional), the DICOM headers (pydicom), the FHIR JSON,
the operator's dispatch log and the claim lines. A header the injector changed
is therefore seen exactly as a reviewer would see it.

Output: <out>/warehouse/*.csv, one file per table in docs/data-dictionary.md.
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import hl7

from flow import modality, writers


def _dtm(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 14:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}:{s[12:14]}"
    if len(s) >= 8:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _parse(path: Path):
    text = path.read_bytes().decode("utf-8")
    return hl7.parse(text)


def _field(seg, n: int) -> str:
    try:
        return str(seg[n])
    except IndexError:
        return ""


def _comp(seg, n: int, c: int, rep: int = 0) -> str:
    """Component c (1-based) of repetition rep of field n."""
    try:
        f = seg[n]
        r = f[rep]
        try:
            return str(r[c - 1])
        except IndexError:
            return ""
    except (IndexError, TypeError):
        return ""


def _segments(msg, name: str) -> list:
    try:
        return msg.segments(name)
    except KeyError:
        return []


def _laterality_from_service_text(text: str) -> tuple[str, str]:
    for suffix, side in ((" LT", "L"), (" RT", "R")):
        if text.endswith(suffix):
            return text[: -len(suffix)], side
    return text, ""


def _prt_person(msg, participation: str) -> str:
    for prt in _segments(msg, "PRT"):
        if _comp(prt, 4, 1) == participation:
            return _comp(prt, 5, 1)
    return ""


def run(out: Path) -> Path:
    out = Path(out)
    wh = out / "warehouse"
    if wh.exists():
        shutil.rmtree(wh)
    wh.mkdir()

    # Reference tables and operator files are copied as they are.
    shutil.copy(out / "registry" / "providers.csv", wh / "providers.csv")
    shutil.copy(out / "dispatch" / "dispatch_log.csv", wh / "dispatch.csv")
    shutil.copy(out / "dispatch" / "trips.csv", wh / "trips.csv")
    shutil.copy(out / "claims" / "claim_lines.csv", wh / "claim_lines.csv")

    # Registration and coverage from the ADT^A04 v2.8 messages.
    patients, coverage = [], []
    for f in sorted((out / "hl7" / "adt" / "v2.8").glob("*.hl7")):
        m = _parse(f)
        pid = m.segment("PID")
        pv1 = m.segment("PV1")
        mrn = _comp(pid, 3, 1)
        patients.append({"mrn": mrn, "family": _comp(pid, 5, 1), "given": _comp(pid, 5, 2), "birth_date": _dtm(_field(pid, 7)), "sex": _field(pid, 8), "facility_id": _comp(pv1, 3, 1), "admitted": _dtm(_field(pv1, 44))})
        for in1 in _segments(m, "IN1"):
            coverage.append({"mrn": mrn, "set_id": _field(in1, 1), "payer_id": _comp(in1, 2, 1), "payer_name": _comp(in1, 2, 2), "plan_type": _field(in1, 15), "priority": _field(in1, 22), "member_id": _field(in1, 36), "start_date": _dtm(_field(in1, 12)), "end_date": _dtm(_field(in1, 13))})
    writers.write_csv(wh / "patients.csv", patients, ["mrn", "family", "given", "birth_date", "sex", "facility_id", "admitted"])
    writers.write_csv(wh / "coverage.csv", coverage, ["mrn", "set_id", "payer_id", "payer_name", "plan_type", "priority", "member_id", "start_date", "end_date"])

    # Orders from the OMI^O23 v2.8 messages.
    orders = []
    for f in sorted((out / "hl7" / "orders" / "v2.8").glob("*.hl7")):
        m = _parse(f)
        pid, orc, obr, ipc = m.segment("PID"), m.segment("ORC"), m.segment("OBR"), m.segment("IPC")
        tq1 = _segments(m, "TQ1")
        desc, side = _laterality_from_service_text(_comp(obr, 4, 2))
        orders.append({
            "accession": _comp(ipc, 1, 1), "placer_order_number": _comp(orc, 2, 1), "filler_order_number": _comp(orc, 3, 1), "mrn": _comp(pid, 3, 1),
            "control": _field(orc, 1), "order_status": _field(orc, 5), "order_datetime": _dtm(_field(orc, 9)), "scheduled_datetime": _dtm(_field(tq1[0], 7)) if tq1 else "",
            "cpt": _comp(obr, 4, 1), "description": desc, "laterality": side, "ordering_npi": _prt_person(m, "OP"), "reason": _comp(obr, 31, 2),
            "study_uid": _comp(ipc, 3, 1), "modality": _comp(ipc, 5, 1),
        })
    writers.write_csv(wh / "orders.csv", orders, ["accession", "placer_order_number", "filler_order_number", "mrn", "control", "order_status", "order_datetime", "scheduled_datetime", "cpt", "description", "laterality", "ordering_npi", "reason", "study_uid", "modality"])

    # Reports from the ORU^R01 v2.8 messages.
    reports = []
    for f in sorted((out / "hl7" / "reports" / "v2.8").glob("*.hl7")):
        m = _parse(f)
        pid, orc, obr = m.segment("PID"), m.segment("ORC"), m.segment("OBR")
        obx = _segments(m, "OBX")
        reports.append({
            "placer_order_number": _comp(orc, 2, 1), "filler_order_number": _comp(orc, 3, 1), "mrn": _comp(pid, 3, 1), "cpt": _comp(obr, 4, 1),
            "exam_datetime": _dtm(_field(obr, 7)), "report_datetime": _dtm(_field(obr, 22)), "status": _field(obr, 25), "reader_npi": _prt_person(m, "PP"),
            "text": _field(obx[0], 5) if obx else "",
        })
    writers.write_csv(wh / "reports.csv", reports, ["placer_order_number", "filler_order_number", "mrn", "cpt", "exam_datetime", "report_datetime", "status", "reader_npi", "text"])

    # DICOM headers.
    paths = sorted((out / "dicom").rglob("*.dcm"))
    rows = modality.read_headers(paths)
    for r in rows:
        r["study_folder"] = Path(r["path"]).parent.name
        r["study_datetime"] = _dtm(r["study_datetime"])
    writers.write_csv(wh / "dicom_instances.csv", rows, ["study_folder", "accession", "patient_id", "patient_name", "birth_date", "sex", "study_uid", "series_uid", "sop_uid", "study_datetime", "body_part_examined", "body_part_tag_present", "laterality", "image_laterality", "view_position", "modality", "referring_physician"])

    # FHIR.
    studies, drs = [], []
    for f in sorted((out / "fhir").glob("*.json")) if (out / "fhir").exists() else []:
        b = json.loads(f.read_text(encoding="utf-8"))
        st, dr = b["ImagingStudy"], b["DiagnosticReport"]
        acsn = next((i["value"] for i in st.get("identifier", []) if i.get("type", {}).get("coding", [{}])[0].get("code") == "ACSN"), "")
        series = st["series"][0]
        studies.append({"accession": acsn, "study_uid": st["identifier"][0]["value"].replace("urn:oid:", ""), "based_on": st["basedOn"][0]["reference"], "number_of_instances": st["numberOfInstances"], "body_site": series["bodySite"]["code"], "laterality_code": series.get("laterality", {}).get("code", ""), "started": st["started"]})
        drs.append({"accession": dr["identifier"][0]["value"], "status": dr["status"], "effective": dr["effectiveDateTime"], "issued": dr["issued"], "conclusion": dr["conclusion"], "imaging_study": dr["imagingStudy"][0]["reference"]})
    writers.write_csv(wh / "fhir_imagingstudy.csv", studies, ["accession", "study_uid", "based_on", "number_of_instances", "body_site", "laterality_code", "started"])
    writers.write_csv(wh / "fhir_diagnosticreport.csv", drs, ["accession", "status", "effective", "issued", "conclusion", "imaging_study"])
    return wh
