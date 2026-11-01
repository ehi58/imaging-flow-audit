"""Hop 5: FHIR R4 resources for an exam: ServiceRequest, ImagingStudy and
DiagnosticReport, as plain JSON (validated against the R4B models in tests;
R4B and R4 agree on every element used here).

The accession travels as an ImagingStudy identifier of type ACSN
(http://terminology.hl7.org/CodeSystem/v2-0203), the same key the HL7 messages
and the claim lines carry.
"""
from __future__ import annotations

from flow.hl7_messages import ReportFacts
from flow.orders import Exam
from flow.registration import Patient

V2_0203 = "http://terminology.hl7.org/CodeSystem/v2-0203"
SNOMED = "http://snomed.info/sct"
LATERALITY = {"L": ("7771000", "Left"), "R": ("24028007", "Right")}
ACSN_SYSTEM = "urn:oid:1.2.826.0.1.3680043.8.498.1"  # the synthetic RIS's accession namespace


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S-05:00")


def resources(patient: Patient, exam: Exam, report: ReportFacts, *, instance_count: int) -> dict[str, dict]:
    patient_ref = {"reference": f"Patient/{patient.mrn}", "display": f"{patient.family}, {patient.given}"}
    sr_id = f"sr-{exam.placer_order_number}"
    study_id = f"study-{exam.accession}"
    dr_id = f"dr-{exam.accession}"
    code = {"coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": exam.cpt, "display": exam.description}], "text": exam.description}
    service_request = {
        "resourceType": "ServiceRequest",
        "id": sr_id,
        "identifier": [
            {"type": {"coding": [{"system": V2_0203, "code": "PLAC"}]}, "value": exam.placer_order_number},
            {"type": {"coding": [{"system": V2_0203, "code": "FILL"}]}, "value": exam.filler_order_number},
        ],
        "status": "completed" if exam.control == "NW" else "revoked",
        "intent": "order",
        "code": code,
        "subject": patient_ref,
        "authoredOn": _iso(exam.order_datetime),
        "occurrenceDateTime": _iso(exam.scheduled_datetime),
        "requester": {"identifier": {"system": "http://hl7.org/fhir/sid/us-npi", "value": exam.ordering_npi}, "display": f"{exam.ordering_family}, {exam.ordering_given}"},
        "reasonCode": [{"text": exam.reason}],
    }
    series = {
        "uid": f"{exam.study_instance_uid}.1",
        "number": 1,
        "modality": {"system": "http://dicom.nema.org/resources/ontology/DCM", "code": "DX"},
        "numberOfInstances": instance_count,
        "bodySite": {"system": "http://dicom.nema.org/resources/ontology/DCM", "code": exam.body_part_examined, "display": exam.body_part_examined},
    }
    if exam.laterality in LATERALITY:
        code_, display = LATERALITY[exam.laterality]
        series["laterality"] = {"system": SNOMED, "code": code_, "display": display}
    imaging_study = {
        "resourceType": "ImagingStudy",
        "id": study_id,
        "identifier": [
            {"system": "urn:dicom:uid", "value": f"urn:oid:{exam.study_instance_uid}"},
            {"type": {"coding": [{"system": V2_0203, "code": "ACSN"}]}, "system": ACSN_SYSTEM, "value": exam.accession},
        ],
        "status": "available",
        "subject": patient_ref,
        "started": _iso(exam.exam_datetime),
        "basedOn": [{"reference": f"ServiceRequest/{sr_id}"}],
        "numberOfSeries": 1,
        "numberOfInstances": instance_count,
        "procedureCode": [code],
        "series": [series],
    }
    diagnostic_report = {
        "resourceType": "DiagnosticReport",
        "id": dr_id,
        "identifier": [{"type": {"coding": [{"system": V2_0203, "code": "ACSN"}]}, "system": ACSN_SYSTEM, "value": exam.accession}],
        "basedOn": [{"reference": f"ServiceRequest/{sr_id}"}],
        "status": "final",
        "category": [{"coding": [{"system": V2_0203.replace("v2-0203", "v2-0074"), "code": "RAD"}]}],
        "code": code,
        "subject": patient_ref,
        "effectiveDateTime": _iso(report.exam_datetime),
        "issued": _iso(report.report_datetime),
        "performer": [{"identifier": {"system": "http://hl7.org/fhir/sid/us-npi", "value": report.radiologist_npi}, "display": f"{report.radiologist_family}, {report.radiologist_given}"}],
        "imagingStudy": [{"reference": f"ImagingStudy/{study_id}"}],
        "conclusion": report.text,
    }
    return {"ServiceRequest": service_request, "ImagingStudy": imaging_study, "DiagnosticReport": diagnostic_report}
