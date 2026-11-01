"""Hop 4: the report for every performed exam.

The body is always the fixed template; nothing reads an image. The turnaround
in clean data sits between 30 minutes and the SLA, so the clean run gives E09
nothing to flag; the injector makes the outliers.
"""
from __future__ import annotations

import random
from datetime import timedelta

from flow.hl7_messages import ReportFacts
from flow.orders import Exam
from flow.registry import Provider

REPORT_TEXT = "SYNTHETIC - NOT A READ"


def build(performed: list[Exam], providers: list[Provider], rng: random.Random, *, sla_hours: int) -> dict[str, ReportFacts]:
    radiologists = [p for p in providers if p.role == "radiologist"]
    if not radiologists:
        raise ValueError("the registry needs radiologists")
    out: dict[str, ReportFacts] = {}
    max_minutes = sla_hours * 60 - 1
    for e in performed:
        # Right-skewed inside the SLA: most reads within a few hours, a tail to the limit.
        minutes = int(min(max_minutes, max(30, rng.lognormvariate(5.3, 0.7))))
        rad = rng.choice(radiologists)
        out[e.accession] = ReportFacts(
            exam_datetime=e.exam_datetime,
            report_datetime=e.exam_datetime + timedelta(minutes=minutes),
            radiologist_npi=rad.npi,
            radiologist_family=rad.family,
            radiologist_given=rad.given,
            text=REPORT_TEXT,
        )
    return out
