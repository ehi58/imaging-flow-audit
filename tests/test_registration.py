"""Hop 1: registration and coverage from the Synthea sample.

The generator turns Synthea's patients and coverage periods into the flow's
own tables: an MRN per resident, a fictitious facility, and coverage rows whose
payers are the repo's generic payers, with member IDs that follow each payer's
scheme. Medicare years split into fee-for-service and Advantage per resident.
"""
import random
from datetime import date

import pytest

from flow import ids, registration, vocab

WINDOW = (date(2024, 11, 1), date(2026, 10, 31))


@pytest.fixture(scope="module")
def built():
    sample = registration.load_synthea_sample()
    return registration.build(sample, vocab.load(), random.Random(5), window=WINDOW)


def test_every_living_resident_gets_a_unique_mrn_and_a_facility(built):
    mrns = [p.mrn for p in built.patients]
    assert len(mrns) == 2000 and len(set(mrns)) == 2000
    assert all(m.startswith("MRN") and len(m) == 10 and m[3:].isdigit() for m in mrns)
    facilities = {f.facility_id for f in vocab.load().facilities}
    assert all(p.facility_id in facilities for p in built.patients)


def test_patients_keep_synthea_identity_fields_and_nothing_else(built):
    p = built.patients[0]
    assert set(p.__dict__) == {"mrn", "synthea_id", "family", "given", "birth_date", "sex", "facility_id", "admitted"}
    assert p.sex in ("M", "F") and isinstance(p.birth_date, date) and p.admitted < WINDOW[0]


def test_coverage_rows_use_the_generic_payers_and_valid_member_ids(built):
    payers = {p.payer_id: p for p in vocab.load().payers}
    assert built.coverage, "no coverage rows"
    for c in built.coverage:
        assert c.payer_id in payers
        scheme = ids.MemberIdScheme(payers[c.payer_id].member_id_prefix, payers[c.payer_id].member_id_digits)
        assert ids.is_valid_member_id(c.member_id, scheme), c
        assert c.start_date <= c.end_date and c.priority in (1, 2)


def test_coverage_periods_overlap_the_study_window(built):
    assert all(c.end_date >= WINDOW[0] and c.start_date <= WINDOW[1] for c in built.coverage)


def test_a_resident_keeps_one_member_id_per_payer(built):
    seen: dict[tuple[str, str], set[str]] = {}
    for c in built.coverage:
        seen.setdefault((c.mrn, c.payer_id), set()).add(c.member_id)
    assert all(len(v) == 1 for v in seen.values())


def test_medicare_splits_into_fee_for_service_and_advantage(built):
    plan_types = {p.payer_id: p.plan_type for p in vocab.load().payers}
    primaries = [plan_types[c.payer_id] for c in built.coverage if c.priority == 1]
    ffs = primaries.count("MEDICARE_FFS")
    ma = primaries.count("MEDICARE_ADVANTAGE")
    assert ffs > 0 and ma > 0
    assert 0.35 < ma / (ffs + ma) < 0.65


def test_dual_eligibles_carry_medicaid_as_secondary(built):
    by_mrn: dict[str, list] = {}
    for c in built.coverage:
        by_mrn.setdefault(c.mrn, []).append(c)
    duals = [rows for rows in by_mrn.values() if any(r.payer_id == "MCD" and r.priority == 2 for r in rows)]
    assert duals, "no dual-eligible resident found"
    for rows in duals:
        assert any(r.priority == 1 and r.payer_id in ("MCR", "MAA", "MAB") for r in rows)


def test_some_residents_have_a_part_a_stay_inside_their_medicare_coverage(built):
    stays = [c for c in built.coverage if c.part_a_stay_start is not None]
    assert stays
    for c in stays:
        assert c.payer_id in ("MCR", "MAA", "MAB") and c.priority == 1
        assert c.start_date <= c.part_a_stay_start <= c.part_a_stay_end <= c.end_date


def test_build_is_deterministic():
    sample = registration.load_synthea_sample()
    a = registration.build(sample, vocab.load(), random.Random(9), window=WINDOW)
    b = registration.build(sample, vocab.load(), random.Random(9), window=WINDOW)
    assert [(c.mrn, c.payer_id, c.member_id, c.start_date) for c in a.coverage] == [
        (c.mrn, c.payer_id, c.member_id, c.start_date) for c in b.coverage
    ]
