"""Hop 1: registration and coverage.

Input: the committed Synthea sample (data/synthea-sample/). Output: the flow's
residents and their coverage periods, with the repo's generic payers and
member IDs that follow each payer's scheme.

Payer mapping. Synthea gives yearly periods with a primary and sometimes a
secondary payer, by generic name:

    Medicare             -> MCR (fee-for-service) or MAA/MAB (Advantage), chosen
                            per resident and kept across periods; a small share
                            switch plans at a period boundary
    Medicare + Commercial Plan A (secondary) -> as above, with CPA as a
                            supplemental secondary
    Dual Eligible        -> Medicare primary as above, MCD secondary
    Medicaid             -> MCD primary
    Commercial Plan A/B  -> CPA/CPB primary
    NO_INSURANCE         -> no coverage row

Synthea v4 already writes day-level START_DATE/END_DATE, so no year-to-day
assignment is needed; periods are clipped to the study window.

A share of Medicare residents get one Part A skilled-nursing stay inside a
Medicare period. It is carried on the coverage row and read by no rule yet
(docs/error-catalog.md, E07, "not encoded").
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from flow import ids
from flow.vocab import Vocab

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "synthea-sample"

MA_SHARE = 0.5          # share of Medicare residents in an Advantage plan
PLAN_SWITCH_SHARE = 0.06  # share of Medicare residents who switch FFS<->MA at a period boundary
PART_A_STAY_SHARE = 0.12  # share of Medicare residents with one Part A stay in the window


@dataclass(frozen=True)
class Patient:
    mrn: str
    synthea_id: str
    family: str
    given: str
    birth_date: date
    sex: str
    facility_id: str
    admitted: date


@dataclass(frozen=True)
class Coverage:
    coverage_id: str
    mrn: str
    payer_id: str
    member_id: str
    priority: int
    start_date: date
    end_date: date
    part_a_stay_start: date | None = None
    part_a_stay_end: date | None = None


@dataclass(frozen=True)
class SyntheaSample:
    patients: list[dict[str, str]]
    periods: list[dict[str, str]]
    payer_names: dict[str, str]


@dataclass(frozen=True)
class Registration:
    patients: list[Patient]
    coverage: list[Coverage]


def load_synthea_sample(folder: Path = SAMPLE) -> SyntheaSample:
    def rows(name: str) -> list[dict[str, str]]:
        with (folder / name).open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    payer_names = {r["Id"]: r["NAME"] for r in rows("payers.csv")}
    return SyntheaSample(rows("patients.csv"), rows("payer_transitions.csv"), payer_names)


def _d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def _strip_synthea_digits(name: str) -> str:
    # Synthea appends digits to names (Carlo647). The digits are not a name.
    return "".join(ch for ch in name if not ch.isdigit())


def build(sample: SyntheaSample, vocab: Vocab, rng: random.Random, *, window: tuple[date, date]) -> Registration:
    w0, w1 = window
    facilities = vocab.facilities
    patients: list[Patient] = []
    coverage: list[Coverage] = []
    mrn_base = rng.randrange(1_000_000, 8_000_000)
    member_ids: dict[tuple[str, str], str] = {}

    def member_id(mrn: str, payer_id: str) -> str:
        key = (mrn, payer_id)
        if key not in member_ids:
            p = vocab.payer(payer_id)
            member_ids[key] = ids.make_member_id(ids.MemberIdScheme(p.member_id_prefix, p.member_id_digits), rng)
        return member_ids[key]

    periods_by_patient: dict[str, list[dict[str, str]]] = {}
    for r in sample.periods:
        periods_by_patient.setdefault(r["PATIENT"], []).append(r)

    ordered = sorted(sample.patients, key=lambda r: r["Id"])
    for i, row in enumerate(ordered):
        mrn = f"MRN{mrn_base + i:07d}"
        admitted = w0 - timedelta(days=rng.randrange(30, 900))
        patients.append(
            Patient(
                mrn=mrn,
                synthea_id=row["Id"],
                family=_strip_synthea_digits(row["LAST"]).upper(),
                given=_strip_synthea_digits(row["FIRST"]).upper(),
                birth_date=_d(row["BIRTHDATE"]),
                sex=row["GENDER"].upper(),
                facility_id=rng.choice(facilities).facility_id,
                admitted=admitted,
            )
        )
        # One Medicare plan per resident, sticky; a few switch once.
        medicare_plan = rng.choice(["MAA", "MAB"]) if rng.random() < MA_SHARE else "MCR"
        switches = rng.random() < PLAN_SWITCH_SHARE
        periods = sorted(periods_by_patient.get(row["Id"], []), key=lambda r: r["START_DATE"])
        n_in_window = 0
        for k, per in enumerate(periods):
            start, end = _d(per["START_DATE"]), _d(per["END_DATE"]) - timedelta(days=1)
            if end < w0 or start > w1:
                continue
            start, end = max(start, w0), min(end, w1)
            n_in_window += 1
            if switches and n_in_window == 2:
                medicare_plan = "MCR" if medicare_plan != "MCR" else rng.choice(["MAA", "MAB"])
            primary_name = sample.payer_names[per["PAYER"]]
            secondary_name = sample.payer_names.get(per["SECONDARY_PAYER"], "")
            rows_out: list[tuple[str, int]] = []
            if primary_name == "Medicare":
                rows_out.append((medicare_plan, 1))
                if secondary_name == "Commercial Plan A":
                    rows_out.append(("CPA", 2))
                elif secondary_name == "Commercial Plan B":
                    rows_out.append(("CPB", 2))
            elif primary_name == "Dual Eligible":
                rows_out.append((medicare_plan, 1))
                rows_out.append(("MCD", 2))
            elif primary_name == "Medicaid":
                rows_out.append(("MCD", 1))
            elif primary_name == "Commercial Plan A":
                rows_out.append(("CPA", 1))
            elif primary_name == "Commercial Plan B":
                rows_out.append(("CPB", 1))
            else:  # NO_INSURANCE
                continue
            for payer_id, priority in rows_out:
                coverage.append(
                    Coverage(
                        coverage_id=f"COV{len(coverage) + 1:07d}",
                        mrn=mrn,
                        payer_id=payer_id,
                        member_id=member_id(mrn, payer_id),
                        priority=priority,
                        start_date=start,
                        end_date=end,
                    )
                )

    # Part A stays: one per selected Medicare resident, inside one primary Medicare period.
    by_mrn: dict[str, list[int]] = {}
    for idx, c in enumerate(coverage):
        if c.priority == 1 and c.payer_id in ("MCR", "MAA", "MAB") and (c.end_date - c.start_date).days >= 90:
            by_mrn.setdefault(c.mrn, []).append(idx)
    for mrn in sorted(by_mrn):
        if rng.random() >= PART_A_STAY_SHARE:
            continue
        idx = rng.choice(by_mrn[mrn])
        c = coverage[idx]
        length = rng.randrange(20, 61)
        latest_start = c.end_date - timedelta(days=length)
        stay_start = c.start_date + timedelta(days=rng.randrange(0, (latest_start - c.start_date).days + 1))
        coverage[idx] = Coverage(
            c.coverage_id, c.mrn, c.payer_id, c.member_id, c.priority, c.start_date, c.end_date,
            part_a_stay_start=stay_start, part_a_stay_end=stay_start + timedelta(days=length),
        )
    return Registration(patients, coverage)
