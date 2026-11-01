"""The committed vocabularies under data/vocab/, loaded once."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VOCAB = ROOT / "data" / "vocab"


@dataclass(frozen=True)
class Payer:
    payer_id: str
    name: str
    plan_type: str
    member_id_prefix: str
    member_id_digits: int


@dataclass(frozen=True)
class Procedure:
    cpt: str
    description: str
    body_part_examined: str
    sided: bool
    views: int
    modality: str
    weight: int


@dataclass(frozen=True)
class Facility:
    facility_id: str
    name: str
    npi: str
    pos: str
    street: str
    city: str
    state: str
    zip: str
    county: str


@dataclass(frozen=True)
class Vocab:
    payers: list[Payer]
    procedures: list[Procedure]
    facilities: list[Facility]
    body_part_terms: list[str]

    def payer(self, payer_id: str) -> Payer:
        return next(p for p in self.payers if p.payer_id == payer_id)

    def facility(self, facility_id: str) -> Facility:
        return next(f for f in self.facilities if f.facility_id == facility_id)

    def procedure(self, cpt: str) -> Procedure:
        return next(p for p in self.procedures if p.cpt == cpt)


def _rows(name: str) -> list[dict[str, str]]:
    with (VOCAB / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def load() -> Vocab:
    payers = [Payer(r["payer_id"], r["name"], r["plan_type"], r["member_id_prefix"], int(r["member_id_digits"])) for r in _rows("payers.csv")]
    procedures = [
        Procedure(r["cpt"], r["description"], r["body_part_examined"], r["sided"] == "1", int(r["views"]), r["modality"], int(r["weight"]))
        for r in _rows("procedures.csv")
    ]
    facilities = [Facility(**r) for r in _rows("facilities.csv")]
    terms = [r["term"] for r in _rows("body_part_terms.csv")]
    return Vocab(payers, procedures, facilities, terms)
