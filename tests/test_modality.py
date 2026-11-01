"""Hop 3: the modality writes DICOM files with synthetic pixels.

One DX study per exam, one series, one instance per view. The headers carry the
accession, the patient identity and the body part and laterality from the
order, so the audit can compare them. Pixels are a gradient with the word
SYNTHETIC drawn into them; nothing is an image of anything.
"""
import random
from datetime import date, datetime

import pydicom
import pytest

from flow import modality
from flow.orders import Exam
from flow.registration import Patient

PATIENT = Patient("MRN1000001", "syn-1", "ASHFORD", "AVERY", date(1942, 3, 5), "F", "F01", date(2024, 1, 15))
EXAM = Exam(
    accession="ACC00000001",
    placer_order_number="PLC0000001",
    filler_order_number="FIL0000001",
    mrn="MRN1000001",
    trip_id="TRP0000001",
    facility_id="F01",
    order_datetime=datetime(2025, 3, 4, 8, 15),
    scheduled_datetime=datetime(2025, 3, 4, 10, 0),
    exam_datetime=datetime(2025, 3, 4, 10, 12),
    cpt="73562",
    description="Radiologic examination knee 3 views",
    body_part_examined="KNEE",
    laterality="L",
    views=3,
    ordering_npi="1234567893",
    ordering_family="BARLOW",
    ordering_given="BLAKE",
    reason="Fall with left knee pain",
    study_instance_uid="1.2.826.0.1.3680043.8.498.11111111111111111111111111111111",
    control="NW",
)


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    out = tmp_path_factory.mktemp("dicom")
    paths = modality.write_study(PATIENT, EXAM, out, referring="BARLOW^BLAKE", rng=random.Random(1))
    return out, paths


def test_one_instance_per_view_in_one_series(written):
    _, paths = written
    assert len(paths) == 3
    series = {pydicom.dcmread(p).SeriesInstanceUID for p in paths}
    assert len(series) == 1
    assert len({pydicom.dcmread(p).SOPInstanceUID for p in paths}) == 3


def test_headers_carry_the_order_and_the_patient(written):
    _, paths = written
    ds = pydicom.dcmread(paths[0])
    assert ds.AccessionNumber == "ACC00000001"
    assert ds.StudyInstanceUID == EXAM.study_instance_uid
    assert ds.PatientID == "MRN1000001" and str(ds.PatientName) == "ASHFORD^AVERY"
    assert ds.PatientBirthDate == "19420305" and ds.PatientSex == "F"
    assert ds.BodyPartExamined == "KNEE" and ds.Laterality == "L" and ds.ImageLaterality == "L"
    assert ds.Modality == "DX" and ds.StudyDate == "20250304" and ds.StudyTime.startswith("1012")
    assert str(ds.ReferringPhysicianName) == "BARLOW^BLAKE"
    assert ds.SOPClassUID == "1.2.840.10008.5.1.4.1.1.1.1"  # Digital X-Ray Image Storage - For Presentation
    assert ds.ViewPosition in ("AP", "PA", "LAT")


def test_unsided_body_part_has_empty_laterality(tmp_path):
    chest = Exam(**{**EXAM.__dict__, "cpt": "71046", "description": "chest 2 views", "body_part_examined": "CHEST", "laterality": None, "views": 2})
    paths = modality.write_study(PATIENT, chest, tmp_path, referring="BARLOW^BLAKE", rng=random.Random(1))
    ds = pydicom.dcmread(paths[0])
    assert ds.BodyPartExamined == "CHEST" and ds.Laterality == "" and ds.ImageLaterality == ""


def test_pixels_are_synthetic_and_labelled(written):
    _, paths = written
    ds = pydicom.dcmread(paths[0])
    arr = ds.pixel_array
    assert arr.shape == (64, 64) and arr.dtype.kind == "u"
    # The label is drawn at the top rows; a gradient alone would be monotone per row.
    top = arr[2:9, :]
    assert (top == top.max()).sum() > 40, "no SYNTHETIC label pixels found"


def test_writing_is_deterministic(tmp_path):
    a = modality.write_study(PATIENT, EXAM, tmp_path / "a", referring="BARLOW^BLAKE", rng=random.Random(7))
    b = modality.write_study(PATIENT, EXAM, tmp_path / "b", referring="BARLOW^BLAKE", rng=random.Random(7))
    assert [p.read_bytes() for p in a] == [p.read_bytes() for p in b]


def test_header_rows_for_the_warehouse(written):
    _, paths = written
    rows = modality.read_headers(paths)
    assert len(rows) == 3
    assert rows[0]["accession"] == "ACC00000001" and rows[0]["body_part_examined"] == "KNEE" and rows[0]["image_laterality"] == "L"
    assert set(rows[0]) >= {"accession", "patient_id", "study_uid", "series_uid", "sop_uid", "study_datetime", "body_part_examined", "laterality", "image_laterality", "view_position", "modality", "referring_physician"}
