"""Hop 6: claim lines, modelled on CMS-1500 / 837P service lines.

Per performed exam: the technical component (the CPT with modifier TC, plus
LT/RT for a sided exam) and the set-up Q0092. Per trip and patient: one
transport line, R0070 when the stop served one patient, R0075 with the count
modifier when it served more (UN 2, UP 3, UQ 4, UR 5, US 6 or more; Medicare
Claims Processing Manual ch. 13 §90.3.4). The payer is the primary coverage in
force on the date of service; a resident with none is billed SELF.

Charges come from a flat synthetic schedule and are not a fee schedule.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

from flow.orders import Exams
from flow.registration import Coverage
from flow.registry import Provider
from flow.vocab import Vocab

R0075_MODIFIER = {2: "UN", 3: "UP", 4: "UQ", 5: "UR", 6: "US"}

# Synthetic flat charges, chosen to look like a charge master and nothing else.
CHARGES = {
    "71045": 60.0, "71046": 75.0, "74018": 70.0, "73562": 95.0, "73560": 80.0, "73030": 85.0, "73110": 85.0,
    "73130": 85.0, "73610": 85.0, "73630": 85.0, "73502": 110.0, "72100": 120.0, "72070": 110.0,
    "Q0092": 40.0, "R0070": 160.0, "R0075": 160.0,
}


@dataclass
class ClaimLine:
    claim_line_id: str
    claim_id: str
    accession: str | None
    trip_id: str
    mrn: str
    date_of_service: date
    place_of_service: str
    hcpcs: str
    modifiers: list[str] = field(default_factory=list)
    units: int = 1
    ordering_npi: str = ""
    rendering_npi: str = ""
    billing_npi: str = ""
    payer_id: str = "SELF"
    member_id: str = ""
    charge: float = 0.0


def primary_coverage_on(coverage: list[Coverage], mrn: str, dos: date) -> Coverage | None:
    rows = [c for c in coverage if c.mrn == mrn and c.priority == 1 and c.start_date <= dos <= c.end_date]
    return rows[0] if rows else None


def build(ex: Exams, coverage: list[Coverage], providers: list[Provider], vocab: Vocab, rng: random.Random) -> list[ClaimLine]:
    supplier = next(p for p in providers if p.role == "supplier").npi
    facility_pos = {f.facility_id: f.pos for f in vocab.facilities}
    trip_facility = {t.trip_id: t.facility_id for t in ex.trips}
    cov_index: dict[str, list[Coverage]] = {}
    for c in coverage:
        if c.priority == 1:
            cov_index.setdefault(c.mrn, []).append(c)

    lines: list[ClaimLine] = []
    claim_ids: dict[tuple[str, date], str] = {}

    def claim_id(mrn: str, dos: date) -> str:
        key = (mrn, dos)
        if key not in claim_ids:
            claim_ids[key] = f"CLM{len(claim_ids) + 1:07d}"
        return claim_ids[key]

    def payer_for(mrn: str, dos: date) -> tuple[str, str]:
        rows = [c for c in cov_index.get(mrn, []) if c.start_date <= dos <= c.end_date]
        return (rows[0].payer_id, rows[0].member_id) if rows else ("SELF", "")

    def add(**kw) -> None:
        kw["claim_line_id"] = f"LN{len(lines) + 1:08d}"
        kw["claim_id"] = claim_id(kw["mrn"], kw["date_of_service"])
        kw["payer_id"], kw["member_id"] = payer_for(kw["mrn"], kw["date_of_service"])
        kw["rendering_npi"] = kw["billing_npi"] = supplier
        kw["charge"] = CHARGES[kw["hcpcs"]]
        lines.append(ClaimLine(**kw))

    performed = ex.performed
    for e in performed:
        dos = e.exam_datetime.date()
        pos = facility_pos[trip_facility[e.trip_id]]
        mods = ["TC"] + (["LT"] if e.laterality == "L" else ["RT"] if e.laterality == "R" else [])
        add(accession=e.accession, trip_id=e.trip_id, mrn=e.mrn, date_of_service=dos, place_of_service=pos, hcpcs=e.cpt, modifiers=mods, ordering_npi=e.ordering_npi)
        add(accession=e.accession, trip_id=e.trip_id, mrn=e.mrn, date_of_service=dos, place_of_service=pos, hcpcs="Q0092", modifiers=[], ordering_npi=e.ordering_npi)

    patients_per_trip: dict[str, list[tuple[str, date, str]]] = {}
    for e in performed:
        key = e.trip_id
        entry = (e.mrn, e.exam_datetime.date(), e.ordering_npi)
        if entry[0] not in [x[0] for x in patients_per_trip.get(key, [])]:
            patients_per_trip.setdefault(key, []).append(entry)
    for trip_id, patients in patients_per_trip.items():
        n = len(patients)
        pos = facility_pos[trip_facility[trip_id]]
        for mrn, dos, ordering in patients:
            if n == 1:
                add(accession=None, trip_id=trip_id, mrn=mrn, date_of_service=dos, place_of_service=pos, hcpcs="R0070", modifiers=[], ordering_npi=ordering)
            else:
                add(accession=None, trip_id=trip_id, mrn=mrn, date_of_service=dos, place_of_service=pos, hcpcs="R0075", modifiers=[R0075_MODIFIER[min(n, 6)]], ordering_npi=ordering)
    return lines
