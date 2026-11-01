"""Hop 2: the dispatch log and the orders.

A trip is one visit to one facility on one date. Each trip serves one or more
residents of that facility; each exam has an order with an accession, a
procedure from the vocabulary, laterality where the body part is sided, an
ordering practitioner from the registry, and a reason for the study.
"""
import random
from datetime import date

import pytest

from flow import orders, registration, registry, vocab

WINDOW = (date(2025, 1, 1), date(2025, 2, 28))  # two months keeps the test quick


@pytest.fixture(scope="module")
def built():
    v = vocab.load()
    rng = random.Random(21)
    reg = registration.build(registration.load_synthea_sample(), v, rng, window=WINDOW)
    providers = registry.build(rng, n_ordering=30, n_npp=10, n_radiologists=4, n_technologists=12)
    return reg, providers, orders.build(reg, providers, v, rng, window=WINDOW)


def test_trips_fall_on_weekdays_inside_the_window(built):
    _, _, ex = built
    assert ex.trips
    for t in ex.trips:
        assert WINDOW[0] <= t.date <= WINDOW[1] and t.date.weekday() < 5


def test_every_exam_belongs_to_a_resident_of_the_trips_facility(built):
    reg, _, ex = built
    facility_of = {p.mrn: p.facility_id for p in reg.patients}
    trip_facility = {t.trip_id: t.facility_id for t in ex.trips}
    for e in ex.exams:
        assert facility_of[e.mrn] == trip_facility[e.trip_id] == e.facility_id


def test_trips_serve_between_one_and_many_residents_with_a_real_share_of_solo_stops(built):
    _, _, ex = built
    per_trip: dict[str, int] = {}
    for e in ex.exams:
        per_trip[e.trip_id] = per_trip.get(e.trip_id, 0) + 1
    assert all(trip.trip_id in per_trip for trip in ex.trips), "a trip with no exam"
    counts = list(per_trip.values())
    assert min(counts) == 1 and max(counts) >= 4
    solo = sum(1 for c in counts if c == 1) / len(counts)
    assert 0.15 < solo < 0.45


def test_identifiers_are_unique_and_well_formed(built):
    _, _, ex = built
    acc = [e.accession for e in ex.exams]
    assert len(set(acc)) == len(acc) and all(a.startswith("ACC") and len(a) == 11 for a in acc)
    assert len({e.placer_order_number for e in ex.exams}) == len(acc)
    assert len({e.filler_order_number for e in ex.exams}) == len(acc)
    uids = [e.study_instance_uid for e in ex.exams]
    assert len(set(uids)) == len(uids) and all(len(u) <= 64 and u[0] != "0" for u in uids)


def test_procedures_come_from_the_vocabulary_and_sided_ones_carry_a_side(built):
    _, _, ex = built
    v = vocab.load()
    by_cpt = {p.cpt: p for p in v.procedures}
    for e in ex.exams:
        p = by_cpt[e.cpt]
        assert e.body_part_examined == p.body_part_examined and e.views == p.views
        if p.sided:
            assert e.laterality in ("L", "R")
        else:
            assert e.laterality is None


def test_every_procedure_in_the_vocabulary_occurs(built):
    # The vocabulary control from the plan: a code in the vocabulary that never
    # occurs is a dead branch, and a rule written for it would pass quietly.
    _, _, ex = built
    assert {e.cpt for e in ex.exams} == {p.cpt for p in vocab.load().procedures}


def test_orders_are_placed_by_registered_individual_orderers_with_a_reason(built):
    _, providers, ex = built
    orderers = {p.npi for p in providers if p.role in ("ordering_physician", "ordering_npp")}
    for e in ex.exams:
        assert e.ordering_npi in orderers
        assert e.reason and len(e.reason) > 10
        assert e.order_datetime <= e.scheduled_datetime <= e.exam_datetime
        assert e.exam_datetime.date() == next(t.date for t in ex.trips if t.trip_id == e.trip_id)


def test_scale_lands_near_the_plan(built):
    # The plan: about 10,000 exams over 24 months for 2,000 residents, so about
    # 830 in two months, give or take.
    _, _, ex = built
    assert 600 <= len(ex.exams) <= 1100, len(ex.exams)


def test_build_is_deterministic():
    v = vocab.load()
    outs = []
    for _ in range(2):
        rng = random.Random(3)
        reg = registration.build(registration.load_synthea_sample(), v, rng, window=WINDOW)
        providers = registry.build(rng, n_ordering=30, n_npp=10, n_radiologists=4, n_technologists=12)
        ex = orders.build(reg, providers, v, rng, window=WINDOW)
        outs.append([(e.accession, e.mrn, e.cpt, e.study_instance_uid) for e in ex.exams])
    assert outs[0] == outs[1]
