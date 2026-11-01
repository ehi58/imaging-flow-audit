"""Hop 3: the modality writes DICOM files.

One Digital X-Ray (DX) study per exam, one series, one instance per view, with
the headers the audit reads (data-dictionary.md, hop 3). Pixels are synthetic:
a 64 x 64 gradient with the word SYNTHETIC drawn from a 5 x 7 bitmap font. No
anatomy, no real image, and the files say so in Manufacturer and in
ImageComments.

UIDs come from pydicom's `generate_uid` with entropy sources, so the same exam
always produces the same UIDs and the same bytes.
"""
from __future__ import annotations

import io
import random
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from flow import writers
from flow.orders import Exam
from flow.registration import Patient

DX_FOR_PRESENTATION = "1.2.840.10008.5.1.4.1.1.1.1"
VIEW_SEQUENCES = {1: ["AP"], 2: ["AP", "LL"], 3: ["AP", "LL", "RLO"]}
SIZE = 64

# 5 x 7 glyphs, rows top to bottom, 1 = lit.
_FONT = {
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
}


def synthetic_pixels(rng: random.Random, label: str = "SYNTHETIC") -> np.ndarray:
    base = np.linspace(200, 3800, SIZE, dtype=np.float64)
    img = (base[:, None] * 0.6 + base[None, :] * 0.4).astype(np.uint16)
    noise = np.array([[rng.randrange(0, 60) for _ in range(SIZE)] for _ in range(SIZE)], dtype=np.uint16)
    img = np.clip(img + noise, 0, 4000).astype(np.uint16)
    x = 5
    for ch in label:
        glyph = _FONT[ch]
        for r, row in enumerate(glyph):
            for c, bit in enumerate(row):
                if bit == "1":
                    img[2 + r, x + c] = 4095
        x += 6
    return img


def _ts(dt: datetime) -> tuple[str, str]:
    return dt.strftime("%Y%m%d"), dt.strftime("%H%M%S")


def write_study(patient: Patient, exam: Exam, out_dir: Path, *, referring: str, rng: random.Random, override: dict | None = None) -> list[Path]:
    """Write the study's instances under out_dir/<accession>/ and return their paths.

    `override` is the injector's hook for the image hop: keys `accession`,
    `laterality`, `image_laterality`, `body_part` (a value, or None to leave the
    tag out entirely) and `instances` (an instance count other than the views).
    The folder is named by the exam's TRUE accession, so a planted header can be
    found again; the header carries the override.
    """
    override = override or {}
    folder = Path(out_dir) / exam.accession
    folder.mkdir(parents=True, exist_ok=True)
    series_uid = generate_uid(entropy_srcs=[exam.study_instance_uid, "series", "1"])
    study_date, study_time = _ts(exam.exam_datetime)
    n_inst = override.get("instances", exam.views)
    views = VIEW_SEQUENCES.get(n_inst, ["AP"] * n_inst)
    paths: list[Path] = []
    for i, view in enumerate(views, 1):
        sop_uid = generate_uid(entropy_srcs=[exam.study_instance_uid, "instance", str(i)])
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = DX_FOR_PRESENTATION
        meta.MediaStorageSOPInstanceUID = sop_uid
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = Dataset()
        ds.file_meta = meta
        ds.SOPClassUID = DX_FOR_PRESENTATION
        ds.SOPInstanceUID = sop_uid
        ds.StudyInstanceUID = exam.study_instance_uid
        ds.SeriesInstanceUID = series_uid
        ds.StudyDate = ds.SeriesDate = ds.ContentDate = study_date
        ds.StudyTime = ds.SeriesTime = ds.ContentTime = study_time
        ds.AccessionNumber = override.get("accession", exam.accession)
        ds.Modality = "DX"
        ds.Manufacturer = "SYNTHETIC"
        ds.ImageComments = "SYNTHETIC - NOT A REAL IMAGE"
        ds.ReferringPhysicianName = referring
        ds.PatientName = f"{patient.family}^{patient.given}"
        ds.PatientID = patient.mrn
        ds.PatientBirthDate = patient.birth_date.strftime("%Y%m%d")
        ds.PatientSex = patient.sex
        body_part = override.get("body_part", exam.body_part_examined)
        if body_part is not None:
            ds.BodyPartExamined = body_part
        ds.Laterality = override.get("laterality", exam.laterality or "") or ""
        ds.ImageLaterality = override.get("image_laterality", exam.laterality or "") or ""
        ds.ViewPosition = view
        ds.StudyID = exam.filler_order_number
        ds.SeriesNumber = 1
        ds.InstanceNumber = i
        ds.ImageType = ["ORIGINAL", "PRIMARY"]
        ds.PatientOrientation = ["L", "F"]
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.Rows = SIZE
        ds.Columns = SIZE
        ds.BitsAllocated = 16
        ds.BitsStored = 12
        ds.HighBit = 11
        ds.PixelRepresentation = 0
        ds.PixelData = synthetic_pixels(rng).tobytes()
        path = folder / f"{i}.dcm"
        buf = io.BytesIO()
        with warnings.catch_warnings():
            # A planted value (a lower-case body part, an undefined term) is an
            # invalid CS on purpose; pydicom's warning about it is the point.
            warnings.simplefilter("ignore", UserWarning)
            pydicom.dcmwrite(buf, ds, enforce_file_format=True)
        writers.write_bytes(path, buf.getvalue())
        paths.append(path)
    return paths


def read_headers(paths: list[Path]) -> list[dict[str, str]]:
    """The header fields the audit reads, one row per instance."""
    rows = []
    for p in paths:
        ds = pydicom.dcmread(p, stop_before_pixels=True)
        rows.append(
            {
                "path": str(p),
                "accession": str(ds.get("AccessionNumber", "")),
                "patient_id": str(ds.get("PatientID", "")),
                "patient_name": str(ds.get("PatientName", "")),
                "birth_date": str(ds.get("PatientBirthDate", "")),
                "sex": str(ds.get("PatientSex", "")),
                "study_uid": str(ds.get("StudyInstanceUID", "")),
                "series_uid": str(ds.get("SeriesInstanceUID", "")),
                "sop_uid": str(ds.get("SOPInstanceUID", "")),
                "study_datetime": f"{ds.get('StudyDate', '')}{ds.get('StudyTime', '')}",
                "body_part_examined": str(ds.get("BodyPartExamined", "")) if "BodyPartExamined" in ds else "",
                "body_part_tag_present": "1" if "BodyPartExamined" in ds else "0",
                "laterality": str(ds.get("Laterality", "")),
                "image_laterality": str(ds.get("ImageLaterality", "")),
                "view_position": str(ds.get("ViewPosition", "")),
                "modality": str(ds.get("Modality", "")),
                "referring_physician": str(ds.get("ReferringPhysicianName", "")),
            }
        )
    return rows
