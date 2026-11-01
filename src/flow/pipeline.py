"""The pipeline: generate every hop from one seed, write the artifacts, validate
the HL7, hash everything; then extract the artifacts back into the warehouse.

    python -m flow.pipeline generate --seed 20261101 --out data/generated --inject
    python -m flow.pipeline extract  --out data/generated

Order of operations matters for the injector: each error is planted at its hop
BEFORE that hop's artifacts are written, and never after (docs/error-catalog.md).
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from flow import claims, fhir_map, hl7_messages, modality, orders, registration, registry, reports, validate_hl7, vocab, writers
from flow import extract as extract_mod
from flow.registration import Coverage, Patient

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "error_rates.yaml"

REGISTRY_SIZE = dict(n_ordering=30, n_npp=10, n_radiologists=4, n_technologists=12)


@dataclass
class Generated:
    """Everything in memory before it is written; the injector edits this."""

    providers: list
    patients: list[Patient]
    coverage: list[Coverage]
    trips: list
    exams: list
    reports: dict
    claim_lines: list
    # Image-hop edits the injector asks the modality to make, keyed by accession:
    # {"accession": ..., "laterality": ..., "image_laterality": ..., "body_part": ..., "body_part_absent": bool}
    dicom_overrides: dict[str, dict] = field(default_factory=dict)
    # Extra studies with no order (E04): list of (patient, exam-like) tuples.
    extra_studies: list = field(default_factory=list)
    truth: list[dict] = field(default_factory=list)


def _config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def build(seed: int, window: tuple[date, date], *, inject: bool, config: dict | None = None) -> Generated:
    cfg = config or _config()
    v = vocab.load()
    rng = random.Random(seed)
    providers = registry.build(rng, **REGISTRY_SIZE)
    reg = registration.build(registration.load_synthea_sample(), v, rng, window=window)
    ex = orders.build(reg, providers, v, rng, window=window)
    g = Generated(providers, reg.patients, reg.coverage, ex.trips, ex.exams, {}, [])
    if inject:
        from flow import inject_errors

        inject_errors.plant_pre_orders(g, cfg, random.Random(seed + 1))  # E08 on orders (before HL7 and claims)
    g.reports = reports.build([e for e in g.exams if e.control == "NW"], providers, rng, sla_hours=cfg["sla"]["report_turnaround_hours"])
    if inject:
        from flow import inject_errors

        inject_errors.plant_reports(g, cfg, random.Random(seed + 2))
    g.claim_lines = claims.build(orders.Exams(g.trips, g.exams), g.coverage, providers, v, rng)
    if inject:
        from flow import inject_errors

        inject_errors.plant_coverage_and_claims(g, cfg, random.Random(seed + 3))
        inject_errors.plant_images(g, cfg, random.Random(seed + 4))
    return g


def write(g: Generated, out: Path, *, seed: int, window: tuple[date, date], inject: bool, validate: bool) -> dict:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    writers.start_manifest(out)
    v = vocab.load()
    patients = {p.mrn: p for p in g.patients}
    orderers = {p.npi: p for p in g.providers}

    writers.write_csv(out / "registry" / "providers.csv", g.providers, ["npi", "entity_type", "role", "family", "given", "credential", "organization_name", "taxonomy_code", "taxonomy_label"])
    writers.write_csv(out / "registration" / "patients.csv", g.patients, ["mrn", "synthea_id", "family", "given", "birth_date", "sex", "facility_id", "admitted"])
    writers.write_csv(out / "registration" / "coverage.csv", g.coverage, ["coverage_id", "mrn", "payer_id", "member_id", "priority", "start_date", "end_date", "part_a_stay_start", "part_a_stay_end"])
    writers.write_csv(out / "dispatch" / "trips.csv", g.trips, ["trip_id", "date", "facility_id", "technologist_npi"])
    performed = [e for e in g.exams if e.control == "NW"]
    tech_of_trip = {t.trip_id: t.technologist_npi for t in g.trips}
    dispatch_rows = [
        {"trip_id": e.trip_id, "date": e.exam_datetime.date(), "facility_id": e.facility_id, "technologist_npi": tech_of_trip[e.trip_id], "accession": e.accession, "mrn": e.mrn}
        for e in performed
    ]
    writers.write_csv(out / "dispatch" / "dispatch_log.csv", dispatch_rows, ["trip_id", "date", "facility_id", "technologist_npi", "accession", "mrn"])
    writers.write_csv(
        out / "orders" / "orders.csv", g.exams,
        ["accession", "placer_order_number", "filler_order_number", "mrn", "trip_id", "facility_id", "order_datetime", "scheduled_datetime", "exam_datetime", "cpt", "description", "body_part_examined", "laterality", "views", "ordering_npi", "reason", "study_instance_uid", "control"],
    )
    report_rows = [{"accession": acc, **r.__dict__} for acc, r in g.reports.items()]
    writers.write_csv(out / "reports" / "reports.csv", report_rows, ["accession", "exam_datetime", "report_datetime", "radiologist_npi", "radiologist_family", "radiologist_given", "text"])
    writers.write_csv(
        out / "claims" / "claim_lines.csv", g.claim_lines,
        ["claim_line_id", "claim_id", "accession", "trip_id", "mrn", "date_of_service", "place_of_service", "hcpcs", "modifiers", "units", "ordering_npi", "rendering_npi", "billing_npi", "payer_id", "member_id", "charge"],
    )
    if g.truth:
        writers.write_csv(out / "truth" / "planted_errors.csv", g.truth, ["record_key", "record_type", "error_id", "variant", "holdout", "hop", "field", "before", "after"])

    # HL7: ADT per patient, orders and reports per exam, both forms.
    cov_by_mrn: dict[str, list[Coverage]] = {}
    for c in g.coverage:
        cov_by_mrn.setdefault(c.mrn, []).append(c)
    msg_no = 0
    for p in g.patients:
        msg_no += 1
        now = datetime(p.admitted.year, p.admitted.month, p.admitted.day, 10, 5)
        for ver in ("2.8", "2.5.1"):
            text = hl7_messages.adt_a04(p, cov_by_mrn.get(p.mrn, []), v, version=ver, control_id=f"ADT{msg_no:07d}", now=now)
            writers.write_hl7(out / "hl7" / "adt" / f"v{ver}" / f"{p.mrn}.hl7", text)
    for e in g.exams:
        msg_no += 1
        p = patients[e.mrn]
        o = hl7_messages.OrderFacts(
            e.placer_order_number, e.filler_order_number, e.accession, e.study_instance_uid, e.order_datetime, e.scheduled_datetime,
            e.cpt, e.description, e.laterality, e.ordering_npi, e.ordering_family, e.ordering_given, e.reason,
        )
        writers.write_hl7(out / "hl7" / "orders" / "v2.8" / f"{e.accession}.hl7", hl7_messages.order_v28(p, o, v, control_id=f"ORD{msg_no:07d}", now=e.order_datetime, control=e.control))
        writers.write_hl7(out / "hl7" / "orders" / "v2.5.1" / f"{e.accession}.hl7", hl7_messages.order_v251(p, o, v, control_id=f"ORD{msg_no:07d}", now=e.order_datetime, control=e.control))
        r = g.reports.get(e.accession)
        if r is not None:
            msg_no += 1
            writers.write_hl7(out / "hl7" / "reports" / "v2.8" / f"{e.accession}.hl7", hl7_messages.report_v28(p, o, r, v, control_id=f"RPT{msg_no:07d}", now=r.report_datetime))
            writers.write_hl7(out / "hl7" / "reports" / "v2.5.1" / f"{e.accession}.hl7", hl7_messages.report_v251(p, o, r, v, control_id=f"RPT{msg_no:07d}", now=r.report_datetime))
            bundle = fhir_map.resources(p, e, r, instance_count=e.views)
            (out / "fhir").mkdir(exist_ok=True)
            (out / "fhir" / f"{e.accession}.json").write_text(json.dumps(bundle, indent=1) + "\n", encoding="utf-8")

    # DICOM: one study per performed exam, plus the injector's orphans.
    instances = 0
    studies = 0
    pix_rng = random.Random(seed + 7)
    for e in performed:
        p = patients[e.mrn]
        orderer = orderers.get(e.ordering_npi)
        referring = f"{orderer.family}^{orderer.given}" if orderer else f"{e.ordering_family}^{e.ordering_given}"
        override = g.dicom_overrides.get(e.accession)
        paths = modality.write_study(p, e, out / "dicom", referring=referring, rng=pix_rng, override=override)
        instances += len(paths)
        studies += 1
    for p, e, override in g.extra_studies:
        paths = modality.write_study(p, e, out / "dicom", referring=f"{e.ordering_family}^{e.ordering_given}", rng=pix_rng, override=override)
        instances += len(paths)
        studies += 1

    hl7_files = sorted((out / "hl7").rglob("*.hl7"))
    validation: dict = {"hl7_files": len(hl7_files), "hapi": None, "hl7apy_strict": None}
    if validate:
        results = validate_hl7.hapi_validate(hl7_files)
        failed = [r for r in results if not r.ok]
        validation["hapi"] = {"files": len(results), "failed": len(failed), "first_failures": [f"{r.path.name}: {r.detail[:200]}" for r in failed[:5]]}
        # HAPI has validated every file above. hl7apy strict is the second
        # opinion on the v2.5.1 form; it parses at roughly 0.1 s per message, so
        # past 2,000 files it runs on a deterministic 1-in-20 sample.
        v251 = [f for f in hl7_files if f.parent.name == "v2.5.1"]
        step = 1 if len(v251) <= 2000 else 20
        sample = v251[::step]
        bad = 0
        for f in sample:
            if not validate_hl7.hl7apy_strict(f.read_bytes().decode("utf-8")).ok:
                bad += 1
        validation["hl7apy_strict"] = {"files": len(sample), "of": len(v251), "every_nth": step, "failed": bad}
        if failed or bad:
            raise RuntimeError(f"HL7 validation failed: hapi {len(failed)}, hl7apy {bad}; see MANIFEST.json")

    counts = {
        "providers": len(g.providers), "patients": len(g.patients), "coverage": len(g.coverage), "trips": len(g.trips),
        "orders": len(g.exams), "performed": len(performed), "reports": len(g.reports), "studies": studies, "instances": instances,
        "claim_lines": len(g.claim_lines),
        "planted": sum(1 for t in g.truth if t["hop"] != "cascade"),
        "cascade": sum(1 for t in g.truth if t["hop"] == "cascade"),
    }
    sha = writers.manifest()
    manifest = {
        "seed": seed, "window": [window[0].isoformat(), window[1].isoformat()], "inject": inject, "counts": counts,
        "validation": validation, "files": len(sha), "sha256": sha,
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def generate(*, seed: int, window: tuple[date, date], out_dir: Path, inject: bool, validate: bool = True, config: dict | None = None) -> dict:
    g = build(seed, window, inject=inject, config=config)
    return write(g, Path(out_dir), seed=seed, window=window, inject=inject, validate=validate)


def extract(out_dir: Path) -> Path:
    """Read the written artifacts back into warehouse tables; returns the folder."""
    return extract_mod.run(Path(out_dir))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--seed", type=int, default=None)
    gen.add_argument("--out", default="data/generated")
    gen.add_argument("--inject", action="store_true")
    gen.add_argument("--months", type=int, default=None)
    gen.add_argument("--no-validate", action="store_true")
    ext = sub.add_parser("extract")
    ext.add_argument("--out", default="data/generated")
    args = ap.parse_args()
    cfg = _config()
    if args.cmd == "generate":
        seed = args.seed if args.seed is not None else cfg["seed_default"]
        months = args.months or cfg["scale"]["months"]
        end = date(2026, 10, 31)
        start = date(end.year, end.month, 1) - timedelta(days=31 * (months - 1))
        start = date(start.year, start.month, 1)
        m = generate(seed=seed, window=(start, end), out_dir=Path(args.out), inject=args.inject, validate=not args.no_validate, config=cfg)
        print(json.dumps({k: m[k] for k in ("seed", "window", "inject", "counts", "validation", "files")}, indent=1))
    else:
        wh = extract(Path(args.out))
        print(f"warehouse written to {wh}")


if __name__ == "__main__":
    main()
