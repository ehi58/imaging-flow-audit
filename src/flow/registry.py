"""The synthetic provider registry.

Every NPI is Luhn-valid and must be absent from NPPES. Names come from short
fictitious lists, never from a real registry. There is one supplier
organization (the portable x-ray company the flow simulates) and four kinds of
individual: ordering physicians, ordering nonphysician practitioners,
radiologists and technologists.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from flow import ids

SUPPLIER_NAME = "Harborline Portable Imaging"
SUPPLIER_TAXONOMY = ("335V00000X", "Portable X-ray and/or Other Portable Diagnostic Imaging Supplier")

FAMILY_NAMES = [
    "Ashford", "Barlow", "Caldwell", "Danvers", "Ellery", "Fenwick", "Garrow", "Hale", "Ingram", "Jessop",
    "Kestrel", "Larkin", "Merriman", "Norwood", "Oakes", "Pembroke", "Quill", "Ransome", "Selby", "Thorne",
    "Underhill", "Vance", "Whitlock", "Yardley", "Ambrose", "Brightwater", "Colfax", "Dunmore", "Easton", "Fairweather",
]
GIVEN_NAMES = [
    "Avery", "Blake", "Cameron", "Dana", "Ellis", "Frankie", "Gale", "Harper", "Indigo", "Jules",
    "Kit", "Lane", "Morgan", "Noor", "Oriel", "Parker", "Quinn", "Reese", "Sage", "Tatum",
    "Umber", "Vale", "Wren", "Yael", "Zia", "Ari", "Bay", "Cyd", "Dell", "Emery",
]

ROLE_TAXONOMY = {
    "ordering_physician": ("207Q00000X", "Family Medicine"),
    "ordering_npp": ("363L00000X", "Nurse Practitioner"),
    "radiologist": ("2085R0202X", "Diagnostic Radiology"),
    "technologist": ("247100000X", "Radiologic Technologist"),
}
ROLE_CREDENTIAL = {
    "ordering_physician": "MD",
    "ordering_npp": "NP",
    "radiologist": "MD",
    "technologist": "RT(R)",
}


@dataclass(frozen=True)
class Provider:
    npi: str
    entity_type: int  # 1 individual, 2 organization
    role: str
    family: str
    given: str
    credential: str
    organization_name: str
    taxonomy_code: str
    taxonomy_label: str


def build(rng: random.Random, *, n_ordering: int, n_npp: int, n_radiologists: int, n_technologists: int) -> list[Provider]:
    out: list[Provider] = []
    seen: set[str] = set()

    def fresh_npi() -> str:
        while True:
            n = ids.make_npi(rng)
            if n not in seen:
                seen.add(n)
                return n

    out.append(
        Provider(fresh_npi(), 2, "supplier", "", "", "", SUPPLIER_NAME, SUPPLIER_TAXONOMY[0], SUPPLIER_TAXONOMY[1])
    )
    for role, count in (
        ("ordering_physician", n_ordering),
        ("ordering_npp", n_npp),
        ("radiologist", n_radiologists),
        ("technologist", n_technologists),
    ):
        code, label = ROLE_TAXONOMY[role]
        for _ in range(count):
            out.append(
                Provider(
                    fresh_npi(), 1, role, rng.choice(FAMILY_NAMES), rng.choice(GIVEN_NAMES), ROLE_CREDENTIAL[role], "", code, label
                )
            )
    return out


class ControlFailed(AssertionError):
    """The positive control did not fire, so the negative result is not trusted."""


@dataclass
class AbsenceResult:
    absent: list[str]
    assigned: list[str]

    @property
    def ok(self) -> bool:
        return not self.assigned


def check_absent_from_nppes(npis: list[str], lookup: Callable[[str], bool], *, control: str | None = None) -> AbsenceResult:
    """`lookup(npi)` returns True when NPPES holds a record for that NPI.

    With `control`, the lookup must return True for it before any negative is
    believed: a lookup that cannot see reports absence exactly like a lookup
    that looked and found nothing.
    """
    if control is not None and not lookup(control):
        raise ControlFailed(f"the control NPI {control} was not found; the lookup cannot see NPPES")
    absent, assigned = [], []
    for n in npis:
        (assigned if lookup(n) else absent).append(n)
    return AbsenceResult(absent=absent, assigned=assigned)
