"""The HL7 v2 messages the flow writes.

Two forms of each, and which is which:

- **v2.8** is the current structure: ADT^A04 (structure ADT_A01), OMI^O23 for
  the imaging order (ORM^O01 was withdrawn in v2.7; the imaging order carries
  an IPC segment with the accession and the Study Instance UID), and ORU^R01
  for the report. Participants (ordering provider, reading radiologist) go in
  PRT segments; the older XCN fields ORC-12/OBR-16/OBR-32 are still defined in
  v2.8 but marked for backward compatibility, so the v2.8 messages use PRT.
- **v2.5.1** is what most RIS, PACS and modality worklist interfaces still
  send (IHE Scheduled Workflow is written against v2.3.1/v2.5.1): ADT^A04 with
  EVN-1, ORM^O01 with the accession in OBR-18 (the IHE convention) and the
  ordering provider in ORC-12 and OBR-16, ORU^R01 with the reader in OBR-32.

Every field a builder sets is declared in FIELDS_USED with its purpose, and
docs/hl7-field-notes.md is generated from that table plus hl7_spec, so the
notes and the messages cannot drift apart. Field numbers are the standard's
(see er7.py for why that needs saying).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from flow import er7
from flow.registration import Coverage, Patient
from flow.vocab import Vocab

SENDING_FACILITY = "HARBORLINE"
RIS = "RIS"
PACS = "PACS"
ASSIGNING = "HARBORLINE"


@dataclass(frozen=True)
class OrderFacts:
    placer_order_number: str
    filler_order_number: str
    accession: str
    study_instance_uid: str
    order_datetime: datetime
    scheduled_datetime: datetime
    cpt: str
    description: str
    laterality: str | None  # "L", "R", "B" or None
    ordering_npi: str
    ordering_family: str
    ordering_given: str
    reason: str


@dataclass(frozen=True)
class ReportFacts:
    exam_datetime: datetime
    report_datetime: datetime
    radiologist_npi: str
    radiologist_family: str
    radiologist_given: str
    text: str


@dataclass(frozen=True)
class FieldUse:
    purpose: str
    messages: tuple[str, ...]


# (version, segment, field number) -> what the flow puts there and why it matters.
FIELDS_USED: dict[tuple[str, str, int], FieldUse] = {}


def _use(versions: tuple[str, ...], segment: str, number: int, purpose: str, messages: tuple[str, ...]) -> None:
    for v in versions:
        FIELDS_USED[(v, segment, number)] = FieldUse(purpose, messages)


BOTH = ("2.8", "2.5.1")
V28 = ("2.8",)
V251 = ("2.5.1",)

# MSH, every message
_use(BOTH, "MSH", 3, "Sending application (RIS or PACS). Routing, and the first thing an interface engine logs.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "MSH", 4, "Sending facility: the supplier's own code. A claim is billed under this organization.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "MSH", 5, "Receiving application.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "MSH", 6, "Receiving facility.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "MSH", 7, "Date/time the message was created. Timelines in the review start here.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "MSH", 9, "Message type: code ^ trigger event ^ structure. The structure component decides how a receiver parses the rest.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "MSH", 10, "Message control ID, unique per message. Acknowledgements quote it; duplicates are found by it.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "MSH", 11, "Processing ID: P for production. A T here means a test message that must never reach billing.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "MSH", 12, "Version ID. It tells the receiver which field table applies; the two forms in this repo differ here first.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
# EVN
_use(V251, "EVN", 1, "Event type code (A04). Withdrawn in v2.7+, where MSH-9.2 alone carries the event.", ("ADT^A04",))
_use(BOTH, "EVN", 2, "Recorded date/time of the registration event.", ("ADT^A04",))
# PID
_use(BOTH, "PID", 1, "Set ID, 1 for the single PID.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "PID", 3, "Patient identifier list: the MRN with its assigning authority and type MR. The key that joins registration to orders, images and claims (E01, E04).", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "PID", 5, "Patient name, family ^ given. Must match the DICOM PatientName.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "PID", 7, "Date of birth. Payers match eligibility on it; DICOM PatientBirthDate must agree.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "PID", 8, "Administrative sex (CWE in v2.8, IS in v2.5.1). Eligibility and DICOM PatientSex.", ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"))
# PV1
_use(BOTH, "PV1", 2, "Patient class: O (outpatient). A nursing-facility resident's portable exam is billed under Part B unless a Part A stay applies.", ("ADT^A04", "OMI^O23", "ORM^O01"))
_use(BOTH, "PV1", 3, "Assigned patient location: the facility and room. The stop the transport fee is paid for (E12).", ("ADT^A04", "OMI^O23", "ORM^O01"))
_use(BOTH, "PV1", 44, "Admit date/time at the facility.", ("ADT^A04",))
# IN1
_use(BOTH, "IN1", 1, "Set ID, one per coverage row.", ("ADT^A04",))
_use(BOTH, "IN1", 2, "Health plan ID (CWE in v2.8, CE in v2.5.1): the payer code and name. Decides who the claim goes to (E07).", ("ADT^A04",))
_use(BOTH, "IN1", 3, "Insurance company ID.", ("ADT^A04",))
_use(BOTH, "IN1", 4, "Insurance company name.", ("ADT^A04",))
_use(BOTH, "IN1", 12, "Plan effective date. Coverage must be in force on the date of service (E06).", ("ADT^A04",))
_use(BOTH, "IN1", 13, "Plan expiration date (E06).", ("ADT^A04",))
_use(BOTH, "IN1", 15, "Plan type: the generic plan class (Medicare fee-for-service, Advantage, Medicaid, commercial).", ("ADT^A04",))
_use(BOTH, "IN1", 17, "Insured's relationship to patient: SEL, the resident is the insured.", ("ADT^A04",))
_use(BOTH, "IN1", 22, "Coordination-of-benefits priority: 1 primary, 2 secondary. Billing the secondary as primary is E07's hold-out.", ("ADT^A04",))
_use(BOTH, "IN1", 36, "Policy number: the member ID. Must pass the payer's scheme and belong to this patient (E05).", ("ADT^A04",))
# ORC
_use(BOTH, "ORC", 1, "Order control: NW a new order, CA a cancelled one. A cancelled order has no image, report or claim (E04 hold-out).", ("OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "ORC", 2, "Placer order number, the ordering system's key.", ("OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "ORC", 3, "Filler order number, the RIS key.", ("OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "ORC", 5, "Order status: SC scheduled on the order, CA cancelled, CM completed on the report.", ("OMI^O23", "ORM^O01", "ORU^R01"))
_use(V251, "ORC", 7, "Quantity/timing, with the scheduled start in component 4. Withdrawn in v2.7+, replaced by TQ1.", ("ORM^O01",))
_use(BOTH, "ORC", 9, "Date/time of the order transaction.", ("OMI^O23", "ORM^O01", "ORU^R01"))
_use(V251, "ORC", 12, "Ordering provider as XCN with the NPI. Backward-compatible in v2.8; the v2.8 form uses PRT instead. The claim's box 17b must match (E08).", ("ORM^O01",))
# TQ1
_use(V28, "TQ1", 1, "Set ID.", ("OMI^O23",))
_use(V28, "TQ1", 7, "Start date/time: when the exam is scheduled. In v2.5.1 this lived in ORC-7.4.", ("OMI^O23",))
# OBR
_use(BOTH, "OBR", 1, "Set ID.", ("OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "OBR", 2, "Placer order number (same as ORC-2).", ("OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "OBR", 3, "Filler order number (same as ORC-3).", ("OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "OBR", 4, "Universal service identifier: the CPT code and text, with LT/RT in the text for sided exams. The code the claim must bill (E11) and the side the image must show (E02).", ("OMI^O23", "ORM^O01", "ORU^R01"))
_use(BOTH, "OBR", 7, "Observation date/time: when the exam was performed. Turnaround starts here (E09); the claim's date of service must equal this date.", ("ORU^R01",))
_use(V251, "OBR", 16, "Ordering provider (XCN with NPI), repeated from ORC-12 as IHE expects. Withdrawn from use in v2.8 in favour of PRT.", ("ORM^O01", "ORU^R01"))
_use(V251, "OBR", 18, "Placer field 1: the accession number by IHE Scheduled Workflow convention. The key that joins the order to the image, the report and the claim (E01, E04).", ("ORM^O01", "ORU^R01"))
_use(V251, "OBR", 19, "Placer field 2: the requested procedure ID (IHE convention).", ("ORM^O01", "ORU^R01"))
_use(BOTH, "OBR", 22, "Results report/status change date/time: when the report was signed. Turnaround ends here (E09).", ("ORU^R01",))
_use(BOTH, "OBR", 24, "Diagnostic service section: RAD.", ("ORU^R01",))
_use(BOTH, "OBR", 25, "Result status: F, final. A claim should not go out before a final report exists.", ("ORU^R01",))
_use(BOTH, "OBR", 31, "Reason for study: the statement of the patient's condition that 42 CFR 486.106(a)(2) requires on a portable x-ray order.", ("OMI^O23", "ORM^O01"))
_use(V251, "OBR", 32, "Principal result interpreter (NDL): the reading radiologist. The v2.8 form uses PRT.", ("ORU^R01",))
# PRT (v2.8 only)
_use(V28, "PRT", 1, "Participation instance ID.", ("OMI^O23", "ORU^R01"))
_use(V28, "PRT", 2, "Action code: AD, add.", ("OMI^O23", "ORU^R01"))
_use(V28, "PRT", 4, "Participation: OP ordering provider on the order; PP primary performing provider (the reader) on the report. HL7 table 0912.", ("OMI^O23", "ORU^R01"))
_use(V28, "PRT", 5, "Participation person (XCN with NPI). The ordering NPI the claim's box 17b must match (E08); the reader's NPI on the report.", ("OMI^O23", "ORU^R01"))
# IPC (v2.8 only)
_use(V28, "IPC", 1, "Accession identifier. The key that joins order, image, report and claim (E01, E04).", ("OMI^O23",))
_use(V28, "IPC", 2, "Requested procedure ID.", ("OMI^O23",))
_use(V28, "IPC", 3, "Study Instance UID the modality must use, so the PACS study and the order share one identity.", ("OMI^O23",))
_use(V28, "IPC", 4, "Scheduled procedure step ID.", ("OMI^O23",))
_use(V28, "IPC", 5, "Modality: DX.", ("OMI^O23",))
# OBX
_use(BOTH, "OBX", 1, "Set ID.", ("ORU^R01",))
_use(BOTH, "OBX", 2, "Value type: TX, text.", ("ORU^R01",))
_use(BOTH, "OBX", 3, "Observation identifier: the report text section.", ("ORU^R01",))
_use(BOTH, "OBX", 5, "Observation value: the report body. Here always the fixed template SYNTHETIC - NOT A READ.", ("ORU^R01",))
_use(BOTH, "OBX", 11, "Observation result status: F, final.", ("ORU^R01",))
_use(BOTH, "OBX", 14, "Date/time of the observation (the exam).", ("ORU^R01",))


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S")


def _dt(d: date) -> str:
    return d.strftime("%Y%m%d")


def _cx_mrn(mrn: str) -> str:
    return f"{mrn}^^^{ASSIGNING}^MR"


def _xcn(npi: str, family: str, given: str) -> str:
    # XCN: ID ^ family ^ given ^ ^ ^ ^ ^ ^ assigning authority ... component 13 identifier type code NPI
    return f"{npi}^{family}^{given}^^^^^^NPI&2.16.840.1.113883.4.6&ISO^^^^NPI"


def _pid(version: str, p: Patient) -> er7.Segment:
    pid = er7.Segment("PID", version)
    pid.set(1, "1")
    pid.set(3, _cx_mrn(p.mrn))
    pid.set(5, f"{er7.escape(p.family)}^{er7.escape(p.given)}")
    pid.set(7, _dt(p.birth_date))
    pid.set(8, p.sex)
    return pid


def _pv1(version: str, p: Patient, vocab: Vocab, *, admit: bool) -> er7.Segment:
    fac = vocab.facility(p.facility_id)
    pv1 = er7.Segment("PV1", version)
    pv1.set(1, "1")
    pv1.set(2, "O")
    pv1.set(3, f"{fac.facility_id}^^^{ASSIGNING}")
    if admit:
        pv1.set(44, _ts(datetime(p.admitted.year, p.admitted.month, p.admitted.day, 10, 0)))
    return pv1


def _msh(version: str, sending_app: str, receiving_app: str, message_type: str, control_id: str, now: datetime) -> er7.Segment:
    return er7.msh(
        version=version,
        sending_app=sending_app,
        sending_facility=SENDING_FACILITY,
        receiving_app=receiving_app,
        receiving_facility=SENDING_FACILITY,
        timestamp=_ts(now),
        message_type=message_type,
        control_id=control_id,
    )


# ---- ADT^A04 -----------------------------------------------------------------

def adt_a04(p: Patient, coverage: list[Coverage], vocab: Vocab, *, version: str, control_id: str, now: datetime) -> str:
    segs = [_msh(version, RIS, PACS, "ADT^A04^ADT_A01", control_id, now)]
    evn = er7.Segment("EVN", version)
    if version == "2.5.1":
        evn.set(1, "A04")
    evn.set(2, _ts(now))
    segs += [evn, _pid(version, p), _pv1(version, p, vocab, admit=True)]
    for i, c in enumerate(sorted(coverage, key=lambda c: (c.priority, c.start_date)), 1):
        payer = vocab.payer(c.payer_id)
        in1 = er7.Segment("IN1", version)
        in1.set(1, str(i))
        in1.set(2, f"{payer.payer_id}^{er7.escape(payer.name)}^L")
        in1.set(3, payer.payer_id)
        in1.set(4, er7.escape(payer.name))
        in1.set(12, _dt(c.start_date))
        in1.set(13, _dt(c.end_date))
        in1.set(15, payer.plan_type)
        in1.set(17, "SEL")
        in1.set(22, str(c.priority))
        in1.set(36, c.member_id)
        segs.append(in1)
    return er7.message(segs)


# ---- Orders ------------------------------------------------------------------

def _obr_service(o: OrderFacts) -> str:
    text = o.description
    if o.laterality == "L":
        text += " LT"
    elif o.laterality == "R":
        text += " RT"
    return f"{o.cpt}^{er7.escape(text)}^C4"


def _orc(version: str, o: OrderFacts, *, status: str, control: str = "NW") -> er7.Segment:
    orc = er7.Segment("ORC", version)
    orc.set(1, control)
    orc.set(2, f"{o.placer_order_number}^{RIS}")
    orc.set(3, f"{o.filler_order_number}^{RIS}")
    orc.set(5, status)
    orc.set(9, _ts(o.order_datetime))
    return orc


def order_v28(p: Patient, o: OrderFacts, vocab: Vocab, *, control_id: str, now: datetime, control: str = "NW") -> str:
    """OMI^O23 (v2.8): the imaging order with IPC and PRT. `control` is ORC-1: NW new, CA cancelled."""
    segs = [_msh("2.8", RIS, PACS, "OMI^O23^OMI_O23", control_id, now), _pid("2.8", p), _pv1("2.8", p, vocab, admit=False)]
    segs.append(_orc("2.8", o, status="SC" if control == "NW" else "CA", control=control))
    prt = er7.Segment("PRT", "2.8")
    prt.set(1, f"{o.placer_order_number}-OP^{RIS}")
    prt.set(2, "AD")
    prt.set(4, "OP^Ordering Provider^HL70912")
    prt.set(5, _xcn(o.ordering_npi, o.ordering_family, o.ordering_given))
    segs.append(prt)
    tq1 = er7.Segment("TQ1", "2.8")
    tq1.set(1, "1")
    tq1.set(7, _ts(o.scheduled_datetime))
    segs.append(tq1)
    obr = er7.Segment("OBR", "2.8")
    obr.set(1, "1")
    obr.set(2, f"{o.placer_order_number}^{RIS}")
    obr.set(3, f"{o.filler_order_number}^{RIS}")
    obr.set(4, _obr_service(o))
    obr.set(31, f"^{er7.escape(o.reason)}")
    segs.append(obr)
    ipc = er7.Segment("IPC", "2.8")
    ipc.set(1, f"{o.accession}^{RIS}")
    ipc.set(2, f"{o.filler_order_number}-RP1^{RIS}")
    ipc.set(3, f"{o.study_instance_uid}^{RIS}")
    ipc.set(4, f"{o.filler_order_number}-SPS1^{RIS}")
    ipc.set(5, "DX^Digital Radiography^DCM")
    segs.append(ipc)
    return er7.message(segs)


def order_v251(p: Patient, o: OrderFacts, vocab: Vocab, *, control_id: str, now: datetime, control: str = "NW") -> str:
    """ORM^O01 (v2.5.1): the form most RIS/PACS interfaces still send. `control` is ORC-1."""
    segs = [_msh("2.5.1", RIS, PACS, "ORM^O01^ORM_O01", control_id, now), _pid("2.5.1", p), _pv1("2.5.1", p, vocab, admit=False)]
    orc = _orc("2.5.1", o, status="SC" if control == "NW" else "CA", control=control)
    orc.set(7, f"^^^{_ts(o.scheduled_datetime)}")
    orc.set(12, _xcn(o.ordering_npi, o.ordering_family, o.ordering_given))
    segs.append(orc)
    obr = er7.Segment("OBR", "2.5.1")
    obr.set(1, "1")
    obr.set(2, f"{o.placer_order_number}^{RIS}")
    obr.set(3, f"{o.filler_order_number}^{RIS}")
    obr.set(4, _obr_service(o))
    obr.set(16, _xcn(o.ordering_npi, o.ordering_family, o.ordering_given))
    obr.set(18, o.accession)
    obr.set(19, o.filler_order_number)
    obr.set(31, f"^{er7.escape(o.reason)}")
    segs.append(obr)
    return er7.message(segs)


# ---- Reports -------------------------------------------------------------------

def _report_obr(version: str, o: OrderFacts, r: ReportFacts) -> er7.Segment:
    obr = er7.Segment("OBR", version)
    obr.set(1, "1")
    obr.set(2, f"{o.placer_order_number}^{RIS}")
    obr.set(3, f"{o.filler_order_number}^{RIS}")
    obr.set(4, _obr_service(o))
    obr.set(7, _ts(r.exam_datetime))
    obr.set(22, _ts(r.report_datetime))
    obr.set(24, "RAD")
    obr.set(25, "F")
    return obr


def _obx(version: str, r: ReportFacts) -> er7.Segment:
    obx = er7.Segment("OBX", version)
    obx.set(1, "1")
    obx.set(2, "TX")
    obx.set(3, "18748-4^Diagnostic imaging study^LN")
    obx.set(5, er7.escape(r.text))
    obx.set(11, "F")
    obx.set(14, _ts(r.exam_datetime))
    return obx


def report_v28(p: Patient, o: OrderFacts, r: ReportFacts, vocab: Vocab, *, control_id: str, now: datetime) -> str:
    segs = [_msh("2.8", PACS, RIS, "ORU^R01^ORU_R01", control_id, now), _pid("2.8", p)]
    orc = _orc("2.8", o, status="CM")
    segs.append(orc)
    segs.append(_report_obr("2.8", o, r))
    prt = er7.Segment("PRT", "2.8")
    prt.set(1, f"{o.accession}-PP^{PACS}")
    prt.set(2, "AD")
    prt.set(4, "PP^Primary Performing Provider^HL70912")
    prt.set(5, _xcn(r.radiologist_npi, r.radiologist_family, r.radiologist_given))
    segs.append(prt)
    segs.append(_obx("2.8", r))
    return er7.message(segs)


def report_v251(p: Patient, o: OrderFacts, r: ReportFacts, vocab: Vocab, *, control_id: str, now: datetime) -> str:
    segs = [_msh("2.5.1", PACS, RIS, "ORU^R01^ORU_R01", control_id, now), _pid("2.5.1", p)]
    orc = _orc("2.5.1", o, status="CM")
    orc.set(12, _xcn(o.ordering_npi, o.ordering_family, o.ordering_given))
    segs.append(orc)
    obr = _report_obr("2.5.1", o, r)
    obr.set(16, _xcn(o.ordering_npi, o.ordering_family, o.ordering_given))
    obr.set(18, o.accession)
    obr.set(19, o.filler_order_number)
    # NDL: name (CNN) & start & end & point of care ... CNN is ID & family & given
    obr.set(32, f"{r.radiologist_npi}&{r.radiologist_family}&{r.radiologist_given}")
    segs.append(obr)
    segs.append(_obx("2.5.1", r))
    return er7.message(segs)
