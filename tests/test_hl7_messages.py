"""The HL7 messages the flow writes, in the v2.8 form and the older form real
imaging systems still send.

Every builder declares the fields it uses in `hl7_messages.FIELDS_USED`, and
`docs/hl7-field-notes.md` is generated from that table, so the notes cannot
describe a field the messages do not carry. Field positions are checked here
against the standard's numbering (via hl7_spec) and every v2.8 sample is
validated with HAPI; every v2.5.1 sample with hl7apy strict as well.
"""
from datetime import date, datetime

import pytest

from flow import hl7_messages as hm
from flow import hl7_spec, validate_hl7
from flow.registration import Coverage, Patient
from flow.vocab import load as load_vocab

HAVE_HAPI = validate_hl7.hapi_available()

PATIENT = Patient("MRN1000001", "syn-1", "ASHFORD", "AVERY", date(1942, 3, 5), "F", "F01", date(2024, 1, 15))
COVERAGE = [
    Coverage("COV0000001", "MRN1000001", "MCR", "MFS123456782", 1, date(2024, 11, 1), date(2025, 10, 31)),
    Coverage("COV0000002", "MRN1000001", "CPA", "CPA123456781", 2, date(2024, 11, 1), date(2025, 10, 31)),
]
ORDER = hm.OrderFacts(
    placer_order_number="PLC0000001",
    filler_order_number="FIL0000001",
    accession="ACC00000001",
    study_instance_uid="1.2.826.0.1.3680043.10.1234.1",
    order_datetime=datetime(2025, 3, 4, 8, 15),
    scheduled_datetime=datetime(2025, 3, 4, 10, 0),
    cpt="71046",
    description="Radiologic examination chest 2 views",
    laterality=None,
    ordering_npi="1234567893",
    ordering_family="BARLOW",
    ordering_given="BLAKE",
    reason="Cough and fever, resident unable to travel",
)
REPORT = hm.ReportFacts(
    exam_datetime=datetime(2025, 3, 4, 10, 12),
    report_datetime=datetime(2025, 3, 4, 14, 40),
    radiologist_npi=load_vocab().facilities[1].npi,
    radiologist_family="CALDWELL",
    radiologist_given="CAMERON",
    text="SYNTHETIC - NOT A READ",
)
NOW = datetime(2025, 3, 4, 8, 16)


def fields(seg_text: str) -> list[str]:
    return seg_text.split("|")


def segment(msg: str, name: str, nth: int = 0) -> str:
    segs = [s for s in msg.split("\r") if s.startswith(name + "|") or s == name]
    return segs[nth]


# ---- ADT^A04 ---------------------------------------------------------------

def test_adt_a04_v28_places_the_registration_fields_where_the_standard_says():
    msg = hm.adt_a04(PATIENT, COVERAGE, load_vocab(), version="2.8", control_id="MSG1", now=NOW)
    msh = fields(segment(msg, "MSH"))
    assert msh[8] == "ADT^A04^ADT_A01" and msh[11] == "2.8"
    evn = fields(segment(msg, "EVN"))
    assert evn[1] == "" and evn[2] == "20250304081600"  # EVN-1 withdrawn in v2.8
    pid = fields(segment(msg, "PID"))
    assert pid[3] == "MRN1000001^^^HARBORLINE^MR" and pid[5] == "ASHFORD^AVERY" and pid[7] == "19420305" and pid[8] == "F"
    in1 = fields(segment(msg, "IN1", 0))
    assert in1[1] == "1" and in1[2].startswith("MCR^") and in1[12] == "20241101" and in1[13] == "20251031"
    assert in1[22] == "1" and in1[36] == "MFS123456782"
    in1b = fields(segment(msg, "IN1", 1))
    assert in1b[1] == "2" and in1b[22] == "2" and in1b[36] == "CPA123456781"


def test_adt_a04_v251_keeps_evn_1_and_the_same_positions_elsewhere():
    msg = hm.adt_a04(PATIENT, COVERAGE, load_vocab(), version="2.5.1", control_id="MSG1", now=NOW)
    evn = fields(segment(msg, "EVN"))
    assert evn[1] == "A04" and evn[2] == "20250304081600"
    assert fields(segment(msg, "MSH"))[11] == "2.5.1"
    assert fields(segment(msg, "IN1"))[36] == "MFS123456782"
    assert validate_hl7.hl7apy_strict(msg).ok, validate_hl7.hl7apy_strict(msg).detail


# ---- Order: OMI^O23 (v2.8) and ORM^O01 (v2.5.1) ------------------------------

def test_omi_o23_v28_carries_the_accession_in_ipc_and_the_orderer_in_prt():
    msg = hm.order_v28(PATIENT, ORDER, load_vocab(), control_id="MSG2", now=NOW)
    assert fields(segment(msg, "MSH"))[8] == "OMI^O23^OMI_O23"
    orc = fields(segment(msg, "ORC"))
    assert orc[1] == "NW" and orc[2] == "PLC0000001^RIS" and orc[3] == "FIL0000001^RIS" and orc[9] == "20250304081500"
    tq1 = fields(segment(msg, "TQ1"))
    assert tq1[7] == "20250304100000"
    obr = fields(segment(msg, "OBR"))
    assert obr[4] == "71046^Radiologic examination chest 2 views^C4"
    assert obr[31].startswith("^Cough and fever")  # OBR-31 Reason for Study, text component
    prt = fields(segment(msg, "PRT"))
    assert prt[2] == "AD" and prt[4] == "OP^Ordering Provider^HL70912" and prt[5].startswith("1234567893^BARLOW^BLAKE")
    ipc = fields(segment(msg, "IPC"))
    assert ipc[1] == "ACC00000001^RIS" and ipc[3] == "1.2.826.0.1.3680043.10.1234.1^RIS" and ipc[5] == "DX^Digital Radiography^DCM"
    # The standard's order of segments for OMI_O23's ORDER group
    names = [s.split("|")[0] for s in msg.split("\r") if s]
    assert names == ["MSH", "PID", "PV1", "ORC", "PRT", "TQ1", "OBR", "IPC"]


def test_orm_o01_v251_carries_the_accession_in_obr_18_and_the_orderer_in_orc_12_and_obr_16():
    msg = hm.order_v251(PATIENT, ORDER, load_vocab(), control_id="MSG2", now=NOW)
    assert fields(segment(msg, "MSH"))[8] == "ORM^O01^ORM_O01"
    orc = fields(segment(msg, "ORC"))
    assert orc[1] == "NW" and orc[7].startswith("^^^20250304100000") and orc[12].startswith("1234567893^BARLOW^BLAKE")
    obr = fields(segment(msg, "OBR"))
    assert obr[16].startswith("1234567893^BARLOW^BLAKE") and obr[18] == "ACC00000001" and obr[19] == "FIL0000001"
    assert obr[31].startswith("^Cough and fever")
    assert validate_hl7.hl7apy_strict(msg).ok, validate_hl7.hl7apy_strict(msg).detail


def test_sided_order_carries_the_laterality_modifier_in_obr_4_text():
    sided = ORDER.__class__(**{**ORDER.__dict__, "cpt": "73562", "description": "Radiologic examination knee 3 views", "laterality": "L"})
    msg = hm.order_v28(PATIENT, sided, load_vocab(), control_id="MSG3", now=NOW)
    assert fields(segment(msg, "OBR"))[4] == "73562^Radiologic examination knee 3 views LT^C4"


# ---- Report: ORU^R01 -----------------------------------------------------------

def test_oru_r01_v28_report_fields():
    msg = hm.report_v28(PATIENT, ORDER, REPORT, load_vocab(), control_id="MSG4", now=REPORT.report_datetime)
    assert fields(segment(msg, "MSH"))[8] == "ORU^R01^ORU_R01"
    obr = fields(segment(msg, "OBR"))
    assert obr[7] == "20250304101200" and obr[22] == "20250304144000" and obr[24] == "RAD" and obr[25] == "F"
    obx = fields(segment(msg, "OBX"))
    assert obx[2] == "TX" and obx[5] == "SYNTHETIC - NOT A READ" and obx[11] == "F"
    prt = fields(segment(msg, "PRT"))
    assert prt[4] == "PP^Primary Performing Provider^HL70912" and prt[5].startswith(f"{REPORT.radiologist_npi}^CALDWELL^CAMERON")
    names = [s.split("|")[0] for s in msg.split("\r") if s]
    assert names == ["MSH", "PID", "ORC", "OBR", "PRT", "OBX"]


def test_oru_r01_v251_report_fields():
    msg = hm.report_v251(PATIENT, ORDER, REPORT, load_vocab(), control_id="MSG4", now=REPORT.report_datetime)
    obr = fields(segment(msg, "OBR"))
    assert obr[18] == "ACC00000001" and obr[25] == "F" and obr[32].startswith(f"{REPORT.radiologist_npi}&CALDWELL&CAMERON")
    assert validate_hl7.hl7apy_strict(msg).ok, validate_hl7.hl7apy_strict(msg).detail


# ---- HAPI validation of every v2.8 and v2.5.1 sample --------------------------

@pytest.mark.skipif(not HAVE_HAPI, reason="HAPI jars or a JDK are missing")
def test_hapi_accepts_every_message_form(tmp_path):
    v = load_vocab()
    samples = {
        "adt_v28.hl7": hm.adt_a04(PATIENT, COVERAGE, v, version="2.8", control_id="1", now=NOW),
        "adt_v251.hl7": hm.adt_a04(PATIENT, COVERAGE, v, version="2.5.1", control_id="1", now=NOW),
        "omi_v28.hl7": hm.order_v28(PATIENT, ORDER, v, control_id="2", now=NOW),
        "orm_v251.hl7": hm.order_v251(PATIENT, ORDER, v, control_id="2", now=NOW),
        "oru_v28.hl7": hm.report_v28(PATIENT, ORDER, REPORT, v, control_id="3", now=NOW),
        "oru_v251.hl7": hm.report_v251(PATIENT, ORDER, REPORT, v, control_id="3", now=NOW),
    }
    paths = []
    for name, text in samples.items():
        p = tmp_path / name
        p.write_bytes(text.encode("utf-8"))
        paths.append(p)
    results = validate_hl7.hapi_validate(paths)
    assert [(r.ok, r.detail) for r in results] == [(True, "")] * len(paths), results


# ---- The field table behind the notes ---------------------------------------

def test_every_field_the_builders_set_is_declared_and_defined():
    for (version, segment_name, number), use in hm.FIELDS_USED.items():
        info = hl7_spec.field_info(version, segment_name, number)
        assert not info.withdrawn, (version, segment_name, number)
        assert use.purpose and use.messages
