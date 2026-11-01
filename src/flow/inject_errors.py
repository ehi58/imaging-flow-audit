"""The seeded error injector.

Each error type is planted at the hop docs/error-catalog.md names, before that
hop's artifacts are written, and one truth row per plant goes to
truth/planted_errors.csv, which only the scorer reads. Variants rotate so every
variant, the hold-out included, occurs at least once even at a small scale.

Record keys the rules can emit:
- `accession` for order-side plants (E08) and for image-hop plants on a real
  exam (E01, E02, E03); the image rules key on StudyInstanceUID and the scorer
  maps it back to the accession through the orders table.
- `study_uid` for orphan studies (E04), which have no accession to key on.
- `claim_line_id` for claim-side plants (E05, E06, E07, E11, E12).
- `accession` for report plants (E09): the report rules key on the order.
"""
from __future__ import annotations

import random
from datetime import timedelta

from pydicom.uid import generate_uid

from flow import ids
from flow.hl7_messages import ReportFacts
from flow.orders import Exam
from flow.registration import Coverage
from flow.vocab import load as load_vocab


def _allocate(rng: random.Random, eligible: list, spec: dict) -> list[tuple[object, str, int]]:
    """Pick plants from `eligible` at the configured rate and rotate variants."""
    variants = list(spec["variants"]) + [spec["holdout"]]
    n = max(len(variants), round(spec["rate"] * len(eligible)))
    n = min(n, len(eligible))
    chosen = rng.sample(eligible, n)
    out = []
    for i, item in enumerate(chosen):
        v = variants[i % len(variants)]
        out.append((item, v, 1 if v == spec["holdout"] else 0))
    return out


def _truth(g, key: str, rtype: str, eid: str, variant: str, holdout: int, hop: str, field: str, before, after) -> None:
    g.truth.append(
        {"record_key": key, "record_type": rtype, "error_id": eid, "variant": variant, "holdout": holdout, "hop": hop, "field": field, "before": "" if before is None else str(before), "after": "" if after is None else str(after)}
    )


def _cascade(g, key: str, rtype: str, eid: str, variant: str, holdout: int, field: str) -> None:
    """A record the plant is expected to make a rule fire on without being the
    planted record itself: the patient's other claim lines after a coverage
    change, the other lines of a claim sent to the wrong payer, the exam that
    gained an image. Scored as explained flags, never as planted errors
    (tests/test_cascade_truth.py)."""
    _truth(g, key, rtype, eid, variant, holdout, "cascade", field, "", "")


def _with(exam: Exam, **changes) -> Exam:
    return Exam(**{**exam.__dict__, **changes})


def _bump_last_digit(s: str) -> str:
    return s[:-1] + str((int(s[-1]) + 1) % 10)


# ---- E08: order hop --------------------------------------------------------------

def plant_pre_orders(g, cfg: dict, rng: random.Random) -> None:
    spec = cfg["errors"]["E08"]
    registry_npis = {p.npi for p in g.providers}
    supplier = next(p.npi for p in g.providers if p.role == "supplier")
    performed = [e for e in g.exams if e.control == "NW"]
    index = {e.accession: i for i, e in enumerate(g.exams)}
    for exam, variant, holdout in _allocate(rng, performed, spec):
        before = exam.ordering_npi
        if variant == "blank":
            after = ""
        elif variant == "failed_check_digit":
            after = _bump_last_digit(before)
        elif variant == "organization_npi":
            after = supplier
        else:  # unregistered_valid_npi
            after = ids.make_npi(rng)
            while after in registry_npis:
                after = ids.make_npi(rng)
        g.exams[index[exam.accession]] = _with(exam, ordering_npi=after)
        _truth(g, exam.accession, "accession", "E08", variant, holdout, "order", "ordering_npi", before, after)


# ---- E09: report hop -------------------------------------------------------------

def plant_reports(g, cfg: dict, rng: random.Random) -> None:
    spec = cfg["errors"]["E09"]
    sla = timedelta(hours=cfg["sla"]["report_turnaround_hours"])
    eligible = sorted(g.reports)
    for acc, variant, holdout in _allocate(rng, eligible, spec):
        r: ReportFacts = g.reports[acc]
        before = r.report_datetime.isoformat(sep=" ")
        if variant == "beyond_sla":
            after_dt = r.exam_datetime + sla + timedelta(hours=rng.randrange(1, 73), minutes=rng.randrange(0, 60))
        elif variant == "report_before_exam":
            after_dt = r.exam_datetime - timedelta(hours=rng.randrange(1, 7), minutes=rng.randrange(0, 60))
        elif variant == "no_report":
            del g.reports[acc]
            _truth(g, acc, "accession", "E09", variant, holdout, "report", "report_datetime", before, "")
            continue
        else:  # report_at_sla_plus_one_minute
            after_dt = r.exam_datetime + sla + timedelta(minutes=1)
        g.reports[acc] = ReportFacts(**{**r.__dict__, "report_datetime": after_dt})
        _truth(g, acc, "accession", "E09", variant, holdout, "report", "report_datetime", before, after_dt.isoformat(sep=" "))


# ---- E05, E06, E07, E11, E12: coverage and claim hop -------------------------------

def plant_coverage_and_claims(g, cfg: dict, rng: random.Random) -> None:
    v = load_vocab()
    payers = {p.payer_id: p for p in v.payers}
    lines = g.claim_lines
    by_accession = {}
    for l in lines:
        if l.accession and l.hcpcs != "Q0092":
            by_accession[l.accession] = l  # the technical-component line
    taken_lines: set[str] = set()
    # (error id, variant, hold-out, the planted TC line, the planted value) — the
    # cascade rows are written from the FINAL state of the lines at the end of
    # this function, because E07 moves whole claims between payers after E05
    # and E06 have planted.
    grain_plants: list[tuple[str, str, int, object, str]] = []

    # E05: member ID planted on the coverage row and carried to that patient's claim lines.
    spec = cfg["errors"]["E05"]
    cov_index = {c.coverage_id: i for i, c in enumerate(g.coverage)}
    lines_by_mrn_payer: dict[tuple[str, str], list] = {}
    for l in lines:
        lines_by_mrn_payer.setdefault((l.mrn, l.payer_id), []).append(l)
    eligible = [c for c in g.coverage if c.priority == 1 and (c.mrn, c.payer_id) in lines_by_mrn_payer]
    by_payer_members: dict[str, list[str]] = {}
    for c in g.coverage:
        by_payer_members.setdefault(c.payer_id, []).append(c.member_id)
    for cov, variant, holdout in _allocate(rng, eligible, spec):
        p = payers[cov.payer_id]
        before = cov.member_id
        if variant == "wrong_payer_prefix":
            other = rng.choice([x for x in v.payers if x.payer_id != cov.payer_id])
            after = other.member_id_prefix + before[len(p.member_id_prefix):]
        elif variant == "failed_check_digit":
            after = _bump_last_digit(before)
        elif variant == "other_members_id":
            others = [m for m in by_payer_members[cov.payer_id] if m != before]
            after = rng.choice(others) if others else _bump_last_digit(before)
        else:  # truncated_id
            after = before[:-1]
        g.coverage[cov_index[cov.coverage_id]] = Coverage(**{**cov.__dict__, "member_id": after})
        affected = lines_by_mrn_payer[(cov.mrn, cov.payer_id)]
        for l in affected:
            l.member_id = after
        tc = next((l for l in affected if l.accession and l.hcpcs != "Q0092"), affected[0])
        taken_lines.update(l.claim_line_id for l in affected)
        _truth(g, tc.claim_line_id, "claim_line_id", "E05", variant, holdout, "registration", "member_id", before, after)
        grain_plants.append(("E05", variant, holdout, tc, after))

    # E06: the coverage period no longer covers the date of service; the claim still goes to that payer.
    spec = cfg["errors"]["E06"]
    cov_rows: dict[tuple[str, str], list[Coverage]] = {}
    for c in g.coverage:
        cov_rows.setdefault((c.mrn, c.payer_id), []).append(c)
    eligible_tc = [l for l in by_accession.values() if l.payer_id != "SELF" and l.claim_line_id not in taken_lines]
    for tc, variant, holdout in _allocate(rng, eligible_tc, spec):
        dos = tc.date_of_service
        rows = [c for c in cov_rows[(tc.mrn, tc.payer_id)] if c.start_date <= dos <= c.end_date]
        if not rows:
            continue
        c = rows[0]
        before = f"{c.start_date}..{c.end_date}"
        if variant == "after_coverage_end":
            new = Coverage(**{**c.__dict__, "end_date": dos - timedelta(days=rng.randrange(2, 60))})
        elif variant == "before_coverage_start":
            new = Coverage(**{**c.__dict__, "start_date": dos + timedelta(days=rng.randrange(1, 45))})
        elif variant == "end_day_before_service":
            new = Coverage(**{**c.__dict__, "end_date": dos - timedelta(days=1)})
        else:  # gap_between_periods
            new = Coverage(**{**c.__dict__, "end_date": dos - timedelta(days=3)})
            tail = Coverage(**{**c.__dict__, "coverage_id": f"{c.coverage_id}G", "start_date": dos + timedelta(days=3)})
            if tail.start_date <= tail.end_date:
                g.coverage.append(tail)
        if new.start_date > new.end_date:
            continue
        g.coverage[cov_index[c.coverage_id]] = new
        taken_lines.add(tc.claim_line_id)
        _truth(g, tc.claim_line_id, "claim_line_id", "E06", variant, holdout, "registration", "coverage_period", before, f"{new.start_date}..{new.end_date}")
        grain_plants.append(("E06", variant, holdout, tc, ""))

    # E07: the claim goes to the wrong payer for the date of service.
    spec = cfg["errors"]["E07"]
    primaries_by_mrn: dict[str, list[Coverage]] = {}
    secondaries_by_mrn: dict[str, list[Coverage]] = {}
    for c in g.coverage:
        (primaries_by_mrn if c.priority == 1 else secondaries_by_mrn).setdefault(c.mrn, []).append(c)
    member_for: dict[tuple[str, str], str] = {(c.mrn, c.payer_id): c.member_id for c in g.coverage}

    def can(tc, variant) -> str | None:
        plan = payers[tc.payer_id].plan_type if tc.payer_id in payers else None
        if variant == "ffs_billed_while_ma":
            return "MCR" if plan == "MEDICARE_ADVANTAGE" else None
        if variant == "medicaid_primary_for_dual":
            return "MCD" if any(s.payer_id == "MCD" for s in secondaries_by_mrn.get(tc.mrn, [])) and tc.payer_id != "MCD" else None
        if variant == "prior_payer_after_switch":
            prior = [c for c in primaries_by_mrn.get(tc.mrn, []) if c.end_date < tc.date_of_service and c.payer_id != tc.payer_id]
            return max(prior, key=lambda c: c.end_date).payer_id if prior else None
        sec = [s for s in secondaries_by_mrn.get(tc.mrn, []) if s.start_date <= tc.date_of_service <= s.end_date and s.payer_id != "MCD"]
        return sec[0].payer_id if sec else None

    variants = list(spec["variants"]) + [spec["holdout"]]
    pool = [l for l in by_accession.values() if l.payer_id != "SELF" and l.claim_line_id not in taken_lines]
    n_total = max(len(variants), round(spec["rate"] * len(by_accession)))
    per = max(1, n_total // len(variants))
    for variant in variants:
        holdout = 1 if variant == spec["holdout"] else 0
        eligible = [(tc, can(tc, variant)) for tc in pool if tc.claim_line_id not in taken_lines]
        eligible = [(tc, p) for tc, p in eligible if p is not None]
        for tc, new_payer in rng.sample(eligible, min(per, len(eligible))):
            before = tc.payer_id
            # The whole claim (every line of that patient and date) goes to the
            # wrong payer; one truth row, keyed on the technical-component line.
            for l in lines:
                if l.claim_id == tc.claim_id:
                    l.payer_id = new_payer
                    l.member_id = member_for.get((l.mrn, new_payer), l.member_id)
                    taken_lines.add(l.claim_line_id)
            _truth(g, tc.claim_line_id, "claim_line_id", "E07", variant, holdout, "claim", "payer_id", before, new_payer)
            grain_plants.append(("E07", variant, holdout, tc, new_payer))

    # Cascades of the coverage- and claim-grain plants, from the final lines.
    by_member: dict[str, list] = {}
    by_mrn_payer_final: dict[tuple[str, str], list] = {}
    by_claim: dict[str, list] = {}
    for l in lines:
        if l.payer_id != "SELF":
            by_member.setdefault(l.member_id, []).append(l)
        by_mrn_payer_final.setdefault((l.mrn, l.payer_id), []).append(l)
        by_claim.setdefault(l.claim_id, []).append(l)
    for eid, variant, holdout, tc, after in grain_plants:
        if eid == "E05":
            reach, field = by_member.get(after, []), "member_id"  # every carrier, the borrowed ID's owner included
        elif eid == "E06":
            reach, field = by_mrn_payer_final.get((tc.mrn, tc.payer_id), []), "coverage_period"
        else:
            reach, field = by_claim.get(tc.claim_id, []), "payer_id"
        for l in reach:
            if l.claim_line_id != tc.claim_line_id:
                _cascade(g, l.claim_line_id, "claim_line_id", eid, variant, holdout, field)

    # E11: views billed differ from views taken.
    spec = cfg["errors"]["E11"]
    exam_by_acc = {e.accession: e for e in g.exams}
    swap = {"two_view_billed_one_image": ("71045", "71046"), "single_view_billed_two_images": ("71046", "71045"), "three_views_billed_two_images": ("73560", "73562")}
    variants = list(spec["variants"]) + [spec["holdout"]]
    for variant in variants:
        src, dst = swap[variant]
        eligible = [l for l in by_accession.values() if l.hcpcs == src and l.claim_line_id not in taken_lines]
        share = spec["rate"] / len(variants)
        n = min(len(eligible), max(1, round(share * len(by_accession))))
        for tc in rng.sample(eligible, n):
            tc.hcpcs = dst
            taken_lines.add(tc.claim_line_id)
            _truth(g, tc.claim_line_id, "claim_line_id", "E11", variant, 1 if variant == spec["holdout"] else 0, "claim", "hcpcs", src, dst)

    # E12: the transport line disagrees with the stop.
    spec = cfg["errors"]["E12"]
    transport = [l for l in lines if l.hcpcs in ("R0070", "R0075")]
    by_trip: dict[str, list] = {}
    for l in transport:
        by_trip.setdefault(l.trip_id, []).append(l)
    solo = [ls[0] for ls in by_trip.values() if len(ls) == 1]
    shared = [ls for ls in by_trip.values() if len(ls) >= 2]
    variants = list(spec["variants"]) + [spec["holdout"]]
    n_total = max(len(variants), round(spec["rate"] * len(by_accession)))
    per = max(1, n_total // len(variants))
    next_line = len(lines) + 1
    for variant in variants:
        holdout = 1 if variant == spec["holdout"] else 0
        if variant == "r0075_single_patient":
            for l in rng.sample(solo, min(per, len(solo))):
                l.hcpcs, l.modifiers = "R0075", ["UN"]
                _truth(g, l.claim_line_id, "claim_line_id", "E12", variant, holdout, "claim", "hcpcs", "R0070", "R0075 UN")
        elif variant == "r0070_multi_patient":
            for ls in rng.sample(shared, min(per, len(shared))):
                l = ls[0]
                before = f"{l.hcpcs} {' '.join(l.modifiers)}"
                l.hcpcs, l.modifiers = "R0070", []
                _truth(g, l.claim_line_id, "claim_line_id", "E12", variant, holdout, "claim", "hcpcs", before, "R0070")
        elif variant == "transport_without_exam":
            for l in rng.sample(transport, min(per, len(transport))):
                from flow.claims import ClaimLine

                extra = ClaimLine(
                    claim_line_id=f"LN{next_line:08d}", claim_id=f"{l.claim_id}X", accession=None, trip_id=l.trip_id, mrn=l.mrn,
                    date_of_service=l.date_of_service + timedelta(days=1), place_of_service=l.place_of_service, hcpcs="R0070", modifiers=[],
                    units=1, ordering_npi=l.ordering_npi, rendering_npi=l.rendering_npi, billing_npi=l.billing_npi, payer_id=l.payer_id, member_id=l.member_id, charge=l.charge,
                )
                next_line += 1
                lines.append(extra)
                _truth(g, extra.claim_line_id, "claim_line_id", "E12", variant, holdout, "claim", "date_of_service", "(no line)", str(extra.date_of_service))
        else:  # modifier_count_mismatch
            pool2 = [ls for ls in shared if ls[0].modifiers and ls[0].modifiers[0] in ("UN", "UP", "UQ")]
            for ls in rng.sample(pool2, min(per, len(pool2))):
                l = ls[0]
                before = l.modifiers[0]
                after = {"UN": "UP", "UP": "UN", "UQ": "UP"}[before]
                l.modifiers = [after]
                _truth(g, l.claim_line_id, "claim_line_id", "E12", variant, holdout, "claim", "modifiers", before, after)


# ---- E01, E02, E03, E04: image hop ----------------------------------------------

def plant_images(g, cfg: dict, rng: random.Random) -> None:
    v = load_vocab()
    performed = [e for e in g.exams if e.control == "NW"]
    taken: set[str] = set()
    same_day: dict = {}
    for e in performed:
        same_day.setdefault(e.exam_datetime.date(), []).append(e)

    # E01: the DICOM accession differs from the order's.
    spec = cfg["errors"]["E01"]
    real_accessions = {e.accession for e in g.exams}
    for exam, variant, holdout in _allocate(rng, performed, spec):
        acc = exam.accession
        digits = acc[3:]
        if variant == "transposed_digits":
            i = rng.randrange(0, len(digits) - 1)
            while digits[i] == digits[i + 1]:
                i = (i + 1) % (len(digits) - 1)
            d = list(digits)
            d[i], d[i + 1] = d[i + 1], d[i]
            after = "ACC" + "".join(d)
        elif variant == "prefix_dropped":
            after = digits
        elif variant == "other_same_day_accession":
            others = [o for o in same_day[exam.exam_datetime.date()] if o.mrn != exam.mrn]
            after = rng.choice(others).accession if others else "ACC" + digits[::-1]
        else:  # leading_zero_dropped
            after = "ACC" + digits.lstrip("0") if digits.startswith("0") else "ACC" + digits[1:]
        g.dicom_overrides.setdefault(acc, {})["accession"] = after
        taken.add(acc)
        _truth(g, acc, "accession", "E01", variant, holdout, "image", "AccessionNumber", acc, after)
        if after != acc and after in real_accessions:
            # That exam now holds an image it never took, so E01 and E11 may fire on
            # it. `other_same_day_accession` does this by design; a transposition or
            # a dropped digit can land on a real accession by chance (seen: 2-month
            # seed 77, ACC06998649 -> ACC06998694), and the cascade is the same.
            _cascade(g, after, "accession", "E01", variant, holdout, "AccessionNumber")

    # E02: laterality disagrees with the order (sided exams only).
    spec = cfg["errors"]["E02"]
    sided = [e for e in performed if e.laterality in ("L", "R") and e.accession not in taken]
    for exam, variant, holdout in _allocate(rng, sided, spec):
        other = "R" if exam.laterality == "L" else "L"
        ov = g.dicom_overrides.setdefault(exam.accession, {})
        if variant == "lr_swapped":
            ov["laterality"], ov["image_laterality"], after, field = other, other, other, "ImageLaterality"
        elif variant == "image_laterality_blank":
            ov["laterality"], ov["image_laterality"], after, field = "", "", "", "ImageLaterality"
        elif variant == "bilateral_on_single":
            ov["laterality"], ov["image_laterality"], after, field = "B", "B", "B", "ImageLaterality"
        else:  # laterality_tag_only_wrong
            ov["laterality"], after, field = other, other, "Laterality"
        taken.add(exam.accession)
        _truth(g, exam.accession, "accession", "E02", variant, holdout, "image", field, exam.laterality, after)

    # E03: body part missing or undefined.
    spec = cfg["errors"]["E03"]
    eligible = [e for e in performed if e.accession not in taken]
    for exam, variant, holdout in _allocate(rng, eligible, spec):
        ov = g.dicom_overrides.setdefault(exam.accession, {})
        if variant == "tag_absent":
            ov["body_part"], after = None, "(absent)"
        elif variant == "tag_empty":
            ov["body_part"], after = "", ""
        elif variant == "undefined_term":
            ov["body_part"], after = "TORSO", "TORSO"
        else:  # lowercase_term
            ov["body_part"], after = exam.body_part_examined.lower(), exam.body_part_examined.lower()
        taken.add(exam.accession)
        _truth(g, exam.accession, "accession", "E03", variant, holdout, "image", "BodyPartExamined", exam.body_part_examined, after)

    # E04: a study with no order.
    spec = cfg["errors"]["E04"]
    patients = {p.mrn: p for p in g.patients}
    with_orders = {e.mrn for e in g.exams}
    without_orders = sorted(m for m in patients if m not in with_orders)
    cancelled = [e for e in g.exams if e.control == "CA"]
    variants = list(spec["variants"]) + [spec["holdout"]]
    n_total = max(len(variants), round(spec["rate"] * len(performed)))
    per = max(1, n_total // len(variants))
    chest = v.procedure("71046")
    used_acc = {e.accession for e in g.exams}
    k = 0
    for variant in variants:
        holdout = 1 if variant == spec["holdout"] else 0
        for _ in range(per):
            k += 1
            template = rng.choice(performed)
            if variant == "cancelled_order_accession":
                if not cancelled:
                    break
                orphan = rng.choice(cancelled)
                cancelled.remove(orphan)
                override = None
                key = orphan.study_instance_uid
                after = orphan.accession
            else:
                if variant == "mrn_without_orders" and without_orders:
                    mrn = without_orders.pop(rng.randrange(len(without_orders)))
                else:
                    mrn = template.mrn
                acc = f"ACC9{k:07d}"
                while acc in used_acc:
                    k += 1
                    acc = f"ACC9{k:07d}"
                used_acc.add(acc)
                header_acc = "" if variant == "blank_accession" else acc
                orphan = _with(
                    template, accession=acc, placer_order_number=f"PLC9{k:06d}", filler_order_number=f"FIL9{k:06d}", mrn=mrn,
                    cpt=chest.cpt, description=chest.description, body_part_examined=chest.body_part_examined, laterality=None, views=chest.views,
                    study_instance_uid=generate_uid(entropy_srcs=[acc, "orphan"]), control="NW",
                )
                override = {"accession": header_acc}
                key = orphan.study_instance_uid
                after = header_acc
            g.extra_studies.append((patients[orphan.mrn], orphan, override))
            _truth(g, key, "study_uid", "E04", variant, holdout, "image", "AccessionNumber", "(no order)", after)
