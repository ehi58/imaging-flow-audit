"""The synthetic provider registry.

Every NPI in it passes the check digit and is ABSENT from NPPES. The absence
check runs against a lookup function; in tests it is a fake, and the real one
(scripts/check_nppes.py) queries the NPI Registry API and caches its answers
in data/vocab/nppes_check.json with the date. A known-assigned NPI is the
positive control: the check must reject it.
"""
import random

import pytest

from flow import ids, registry

KNOWN_ASSIGNED = "1234567893"  # the CMS worked example; it is also a real, assigned NPI
SYNTHETIC_FACILITY_NPI = __import__("flow.vocab", fromlist=["load"]).load().facilities[0].npi


def test_registry_is_deterministic_for_a_seed():
    a = registry.build(random.Random(11), n_ordering=10, n_npp=4, n_radiologists=3, n_technologists=6)
    b = registry.build(random.Random(11), n_ordering=10, n_npp=4, n_radiologists=3, n_technologists=6)
    assert [p.npi for p in a] == [p.npi for p in b]


def test_registry_has_each_role_and_one_supplier_organization():
    reg = registry.build(random.Random(2), n_ordering=5, n_npp=2, n_radiologists=2, n_technologists=3)
    roles = {p.role for p in reg}
    assert roles == {"ordering_physician", "ordering_npp", "radiologist", "technologist", "supplier"}
    suppliers = [p for p in reg if p.role == "supplier"]
    assert len(suppliers) == 1 and suppliers[0].entity_type == 2
    assert all(p.entity_type == 1 for p in reg if p.role != "supplier")


def test_every_registry_npi_is_valid_and_unique():
    reg = registry.build(random.Random(3), n_ordering=30, n_npp=10, n_radiologists=4, n_technologists=12)
    npis = [p.npi for p in reg]
    assert len(set(npis)) == len(npis)
    assert all(ids.is_valid_npi(n) for n in npis)


def test_nppes_absence_check_rejects_an_assigned_npi_and_accepts_an_unassigned_one():
    def fake_lookup(npi: str) -> bool:
        # True means NPPES holds a record for this NPI.
        return npi == KNOWN_ASSIGNED

    result = registry.check_absent_from_nppes([KNOWN_ASSIGNED, SYNTHETIC_FACILITY_NPI], fake_lookup)
    assert result.assigned == [KNOWN_ASSIGNED]
    assert result.absent == [SYNTHETIC_FACILITY_NPI]
    assert result.ok is False


def test_nppes_absence_check_requires_the_positive_control_to_fire():
    # A lookup that answers "absent" for everything, including the control,
    # cannot be trusted: the check must fail rather than pass quietly.
    def blind_lookup(npi: str) -> bool:
        return False

    with pytest.raises(registry.ControlFailed):
        registry.check_absent_from_nppes([SYNTHETIC_FACILITY_NPI], blind_lookup, control=KNOWN_ASSIGNED)


def test_registry_names_are_from_the_fictitious_lists_only():
    reg = registry.build(random.Random(4), n_ordering=20, n_npp=5, n_radiologists=3, n_technologists=8)
    for p in reg:
        if p.entity_type == 1:
            assert p.family in registry.FAMILY_NAMES and p.given in registry.GIVEN_NAMES
    supplier = next(p for p in reg if p.role == "supplier")
    assert supplier.organization_name == registry.SUPPLIER_NAME
