"""Hops 4 to 6: reports, FHIR resources and claim lines, built from the orders.

Clean data must give the audit nothing to flag: every performed exam has a
final report inside the SLA, every claim line names the payer in force on the
date of service with that patient's member ID, and every trip's transport line
matches the number of patients seen.
"""
import random
from datetime import date, timedelta

import pytest

from flow import claims, fhir_map, orders, registration, registry, reports, vocab

WINDOW = (date(2025, 1, 1), date(2025, 2, 28))
SLA_HOURS = 24


@pytest.fixture(scope="module")
def built():
    v = vocab.load()
    rng = random.Random(33)
    reg = registration.build(registration.load_synthea_sample(), v, rng, window=WINDOW)
    providers = registry.build(rng, n_ordering=30, n_npp=10, n_radiologists=4, n_technologists=12)
    ex = orders.build(reg, providers, v, rng, window=WINDOW)
    rep = reports.build(ex.performed, providers, rng, sla_hours=SLA_HOURS)
    cl = claims.build(ex, reg.coverage, providers, v, rng)
    return reg, providers, ex, rep, cl


# ---- reports -------------------------------------------------------------------

def test_every_performed_exam_has_one_final_report_inside_the_sla(built):
    _, providers, ex, rep, _ = built
    radiologists = {p.npi for p in providers if p.role == "radiologist"}
    assert set(rep) == {e.accession for e in ex.performed}
    for e in ex.performed:
        r = rep[e.accession]
        assert r.exam_datetime == e.exam_datetime
        assert timedelta(minutes=30) <= r.report_datetime - r.exam_datetime < timedelta(hours=SLA_HOURS)
        assert r.radiologist_npi in radiologists
        assert r.text == "SYNTHETIC - NOT A READ"


def test_cancelled_orders_have_no_report(built):
    _, _, ex, rep, _ = built
    cancelled = [e for e in ex.exams if e.control == "CA"]
    assert cancelled, "the sample should hold a few cancelled orders"
    assert all(e.accession not in rep for e in cancelled)


# ---- claims --------------------------------------------------------------------

def test_each_performed_exam_bills_one_technical_component_and_one_set_up(built):
    _, _, ex, _, cl = built
    by_acc: dict[str, list] = {}
    for line in cl:
        if line.accession:
            by_acc.setdefault(line.accession, []).append(line)
    assert set(by_acc) == {e.accession for e in ex.performed}
    for e in ex.performed:
        lines = by_acc[e.accession]
        tc = [l for l in lines if l.hcpcs == e.cpt]
        setup = [l for l in lines if l.hcpcs == "Q0092"]
        assert len(tc) == 1 and len(setup) == 1 and len(lines) == 2
        assert "TC" in tc[0].modifiers
        if e.laterality == "L":
            assert "LT" in tc[0].modifiers
        elif e.laterality == "R":
            assert "RT" in tc[0].modifiers
        else:
            assert not ({"LT", "RT"} & set(tc[0].modifiers))
        assert tc[0].date_of_service == e.exam_datetime.date() and tc[0].units == 1 and tc[0].charge > 0
        assert tc[0].ordering_npi == e.ordering_npi


def test_transport_lines_match_the_patients_seen_on_each_trip(built):
    _, _, ex, _, cl = built
    patients_per_trip: dict[str, set[str]] = {}
    for e in ex.performed:
        patients_per_trip.setdefault(e.trip_id, set()).add(e.mrn)
    transport = [l for l in cl if l.hcpcs in ("R0070", "R0075")]
    by_trip: dict[str, list] = {}
    for l in transport:
        by_trip.setdefault(l.trip_id, []).append(l)
    assert set(by_trip) == set(patients_per_trip)
    for trip_id, pts in patients_per_trip.items():
        lines = by_trip[trip_id]
        assert {l.mrn for l in lines} == pts and len(lines) == len(pts)
        if len(pts) == 1:
            assert lines[0].hcpcs == "R0070" and not lines[0].modifiers
        else:
            expected = claims.R0075_MODIFIER[min(len(pts), 6)]
            assert all(l.hcpcs == "R0075" and l.modifiers == [expected] for l in lines)


def test_every_line_bills_the_primary_payer_in_force_on_the_date_of_service(built):
    reg, _, _, _, cl = built
    cov = reg.coverage
    for l in cl:
        in_force = [c for c in cov if c.mrn == l.mrn and c.priority == 1 and c.start_date <= l.date_of_service <= c.end_date]
        if in_force:
            assert l.payer_id == in_force[0].payer_id and l.member_id == in_force[0].member_id, l
        else:
            assert l.payer_id == "SELF" and l.member_id == ""


def test_place_of_service_and_billing_identity(built):
    _, providers, ex, _, cl = built
    v = vocab.load()
    supplier = next(p for p in providers if p.role == "supplier").npi
    facility_of_trip = {t.trip_id: t.facility_id for t in ex.trips}
    for l in cl:
        assert l.place_of_service == v.facility(facility_of_trip[l.trip_id]).pos
        assert l.billing_npi == supplier and l.rendering_npi == supplier
    assert len({l.claim_line_id for l in cl}) == len(cl)


def test_claims_are_deterministic():
    v = vocab.load()
    outs = []
    for _ in range(2):
        rng = random.Random(8)
        reg = registration.build(registration.load_synthea_sample(), v, rng, window=WINDOW)
        providers = registry.build(rng, n_ordering=30, n_npp=10, n_radiologists=4, n_technologists=12)
        ex = orders.build(reg, providers, v, rng, window=WINDOW)
        outs.append([(l.claim_line_id, l.hcpcs, l.payer_id, l.charge) for l in claims.build(ex, reg.coverage, providers, v, rng)])
    assert outs[0] == outs[1]


# ---- FHIR ----------------------------------------------------------------------

def test_fhir_resources_validate_as_r4_and_share_the_accession(built):
    reg, _, ex, rep, _ = built
    from fhir.resources.R4B.diagnosticreport import DiagnosticReport
    from fhir.resources.R4B.imagingstudy import ImagingStudy
    from fhir.resources.R4B.servicerequest import ServiceRequest

    patient = {p.mrn: p for p in reg.patients}
    e = ex.performed[0]
    bundle = fhir_map.resources(patient[e.mrn], e, rep[e.accession], instance_count=e.views)
    sr = ServiceRequest.model_validate(bundle["ServiceRequest"])
    study = ImagingStudy.model_validate(bundle["ImagingStudy"])
    dr = DiagnosticReport.model_validate(bundle["DiagnosticReport"])
    acsn = [i for i in study.identifier if i.type and i.type.coding[0].code == "ACSN"]
    assert acsn and acsn[0].value == e.accession
    assert study.basedOn[0].reference == f"ServiceRequest/{sr.id}"
    assert dr.imagingStudy[0].reference == f"ImagingStudy/{study.id}"
    assert dr.status == "final" and dr.conclusion == "SYNTHETIC - NOT A READ"
    assert study.numberOfInstances == e.views and study.series[0].bodySite.display == e.body_part_examined
    if e.laterality:
        assert study.series[0].laterality.code in ("7771000", "24028007")
    assert dr.effectiveDateTime.replace(tzinfo=None) == e.exam_datetime
    assert dr.issued.replace(tzinfo=None) == rep[e.accession].report_datetime
