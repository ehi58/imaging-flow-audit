"""Hop 2: the dispatch log (trips) and the orders (exams).

A trip is one visit by one technologist to one facility on one weekday. Each
trip serves one or more residents of that facility. The share of single-patient
stops matters for the transport fee: R0070 for a solo stop, R0075 with a count
modifier for a shared one (docs/error-catalog.md, E12).

Every exam gets an order: accession, placer and filler numbers, a procedure from
the vocabulary (weighted), a side when the body part is sided, the resident's
attending practitioner as the orderer, and a statement of the condition. About
one order in a hundred is cancelled (ORC-1 CA) and never performed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pydicom.uid import generate_uid

from flow.registration import Registration
from flow.registry import Provider
from flow.vocab import Vocab

P_TRIP_PER_FACILITY_DAY = 0.6
EXAMS_PER_TRIP_WEIGHTS = {1: 28, 2: 25, 3: 20, 4: 14, 5: 8, 6: 5}
CANCELLED_SHARE = 0.01
NPP_ORDERER_SHARE = 0.25

REASONS = {
    "CHEST": [
        "Cough and fever for two days, resident unable to travel",
        "Shortness of breath, rule out pneumonia, bedbound resident",
        "Follow-up of pleural effusion, resident cannot be transported",
        "Suspected aspiration after a choking episode",
    ],
    "ABDOMEN": ["Abdominal distension and no bowel movement for three days", "Feeding tube placement check, bedbound resident"],
    "KNEE": ["Fall from bed with knee pain and swelling", "Knee pain and inability to bear weight after a fall"],
    "SHOULDER": ["Fall with shoulder pain and limited motion", "Shoulder pain after a transfer, rule out fracture"],
    "WRIST": ["Fall on outstretched hand with wrist pain", "Wrist swelling and pain after a fall"],
    "HAND": ["Hand swelling and pain after being caught in a bed rail", "Finger deformity after a fall"],
    "ANKLE": ["Ankle pain and swelling after a fall", "Twisted ankle during a transfer, unable to bear weight"],
    "FOOT": ["Foot pain and swelling, diabetic resident, rule out fracture", "Foot pain after a fall"],
    "HIP": ["Fall with hip pain, unable to bear weight, bedbound resident", "Hip pain after a fall from a wheelchair"],
    "LSPINE": ["Low back pain after a fall, resident cannot be transported", "Back pain and new difficulty standing"],
    "TSPINE": ["Mid-back pain after a fall", "Kyphosis with new back pain, rule out compression fracture"],
}


@dataclass(frozen=True)
class Trip:
    trip_id: str
    date: date
    facility_id: str
    technologist_npi: str


@dataclass(frozen=True)
class Exam:
    accession: str
    placer_order_number: str
    filler_order_number: str
    mrn: str
    trip_id: str
    facility_id: str
    order_datetime: datetime
    scheduled_datetime: datetime
    exam_datetime: datetime
    cpt: str
    description: str
    body_part_examined: str
    laterality: str | None
    views: int
    ordering_npi: str
    ordering_family: str
    ordering_given: str
    reason: str
    study_instance_uid: str
    control: str  # NW performed; CA cancelled, never performed


@dataclass(frozen=True)
class Exams:
    trips: list[Trip]
    exams: list[Exam]

    @property
    def performed(self) -> list[Exam]:
        return [e for e in self.exams if e.control == "NW"]


def _weekdays(w0: date, w1: date):
    d = w0
    while d <= w1:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def build(reg: Registration, providers: list[Provider], vocab: Vocab, rng: random.Random, *, window: tuple[date, date]) -> Exams:
    w0, w1 = window
    physicians = [p for p in providers if p.role == "ordering_physician"]
    npps = [p for p in providers if p.role == "ordering_npp"]
    techs = [p for p in providers if p.role == "technologist"]
    if not (physicians and npps and techs):
        raise ValueError("the registry needs ordering physicians, NPPs and technologists")

    residents_by_facility: dict[str, list[str]] = {}
    for p in reg.patients:
        residents_by_facility.setdefault(p.facility_id, []).append(p.mrn)
    attending: dict[str, Provider] = {}
    for p in reg.patients:
        attending[p.mrn] = rng.choice(npps) if rng.random() < NPP_ORDERER_SHARE else rng.choice(physicians)

    procedures = vocab.procedures
    weights = [p.weight for p in procedures]
    n_weights = list(EXAMS_PER_TRIP_WEIGHTS.items())

    trips: list[Trip] = []
    exams: list[Exam] = []
    # Seven significant digits zero-padded to eight: every accession has a leading
    # zero, which E01's hold-out variant (leading_zero_dropped) depends on.
    acc_base = rng.randrange(1_000_000, 8_000_000)
    plc_base = rng.randrange(1_000_000, 8_000_000)
    fil_base = rng.randrange(1_000_000, 8_000_000)
    n = 0
    for d in _weekdays(w0, w1):
        for fac in vocab.facilities:
            if rng.random() >= P_TRIP_PER_FACILITY_DAY:
                continue
            residents = residents_by_facility.get(fac.facility_id, [])
            if not residents:
                continue
            trip = Trip(f"TRP{len(trips) + 1:07d}", d, fac.facility_id, rng.choice(techs).npi)
            trips.append(trip)
            k = rng.choices([c for c, _ in n_weights], weights=[w for _, w in n_weights])[0]
            k = min(k, len(residents))
            chosen = rng.sample(residents, k)
            start = datetime(d.year, d.month, d.day, 8, 30) + timedelta(minutes=rng.randrange(0, 240))
            for j, mrn in enumerate(chosen):
                n += 1
                proc = rng.choices(procedures, weights=weights)[0]
                side = rng.choice(["L", "R"]) if proc.sided else None
                orderer = attending[mrn]
                scheduled = start + timedelta(minutes=25 * j)
                order_dt = scheduled - timedelta(hours=rng.randrange(2, 30), minutes=rng.randrange(0, 60))
                exam_dt = scheduled + timedelta(minutes=rng.randrange(0, 20))
                accession = f"ACC{acc_base + n:08d}"
                control = "CA" if rng.random() < CANCELLED_SHARE else "NW"
                exams.append(
                    Exam(
                        accession=accession,
                        placer_order_number=f"PLC{plc_base + n:07d}",
                        filler_order_number=f"FIL{fil_base + n:07d}",
                        mrn=mrn,
                        trip_id=trip.trip_id,
                        facility_id=fac.facility_id,
                        order_datetime=order_dt,
                        scheduled_datetime=scheduled,
                        exam_datetime=exam_dt,
                        cpt=proc.cpt,
                        description=proc.description,
                        body_part_examined=proc.body_part_examined,
                        laterality=side,
                        views=proc.views,
                        ordering_npi=orderer.npi,
                        ordering_family=orderer.family,
                        ordering_given=orderer.given,
                        reason=rng.choice(REASONS[proc.body_part_examined]),
                        study_instance_uid=generate_uid(entropy_srcs=[accession, "study"]),
                        control=control,
                    )
                )
    # A trip whose only orders were cancelled still happened (the van went); the
    # transport line for it is what E12's transport_without_exam variant plants,
    # so in the clean data every trip keeps at least one performed exam.
    performed_trips = {e.trip_id for e in exams if e.control == "NW"}
    fixed: list[Exam] = []
    for e in exams:
        if e.control == "CA" and e.trip_id not in performed_trips:
            e = Exam(**{**e.__dict__, "control": "NW"})
            performed_trips.add(e.trip_id)
        fixed.append(e)
    return Exams(trips, fixed)
