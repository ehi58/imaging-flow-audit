"""The audit layer: dbt on DuckDB over the warehouse, then recall scoring.

`run` executes `dbt build` with the warehouse folder and the DuckDB path passed
through environment variables, checks the vocabulary controls, and counts the
rows each rule stored. `score` is the only reader of truth/planted_errors.csv:
per error type and per variant (hold-outs apart) it reports planted, caught,
recall with a Wilson 95% interval, and the flags that match no plant.
"""
from __future__ import annotations

import csv
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DBT_DIR = ROOT / "dbt"
VOCAB_DIR = ROOT / "data" / "vocab"
RULES = ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09", "E11", "E12"]
RULE_TEST = {
    "E01": "E01_accession_mismatch", "E02": "E02_laterality_disagrees", "E03": "E03_body_part_missing_or_undefined",
    "E04": "E04_study_without_order", "E05": "E05_member_id_invalid", "E06": "E06_coverage_not_in_force",
    "E07": "E07_wrong_payer", "E08": "E08_ordering_npi_invalid", "E09": "E09_report_turnaround",
    "E11": "E11_views_billed_vs_taken", "E12": "E12_transport_vs_stop",
}
FAILURE_SCHEMA = "main_dbt_test__audit"
# Rules keyed on the study, whose flags the scorer maps back to the order's accession.
STUDY_KEYED = {"E01", "E02", "E03"}


@dataclass
class AuditResult:
    flags: dict[str, int]
    vocab_controls: dict[str, bool]
    dbt_log: str = ""


def _dbt_executable() -> str:
    here = Path(sys.executable).parent / ("dbt.exe" if os.name == "nt" else "dbt")
    if here.exists():
        return str(here)
    found = shutil.which("dbt")
    if not found:
        raise RuntimeError("dbt not found beside the interpreter or on PATH")
    return found


def _stage_vocab(wh: Path) -> None:
    for name in ("payers", "procedures", "body_part_terms"):
        shutil.copy(VOCAB_DIR / f"{name}.csv", wh / f"vocab_{name}.csv")


def vocabulary_controls(wh: Path) -> dict[str, bool]:
    """Every configured value occurs, and every generated value is configured."""
    con = duckdb.connect()
    q = lambda sql: [r[0] for r in con.execute(sql).fetchall()]  # noqa: E731
    w = wh.as_posix()
    vocab_cpt = set(q(f"select cpt from read_csv('{w}/vocab_procedures.csv', header=true, all_varchar=true)"))
    used_cpt = set(q(f"select distinct cpt from read_csv('{w}/orders.csv', header=true, all_varchar=true)"))
    terms = set(q(f"select term from read_csv('{w}/vocab_body_part_terms.csv', header=true, all_varchar=true)"))
    used_terms = set(q(f"select distinct body_part_examined from read_csv('{w}/dicom_instances.csv', header=true, all_varchar=true) where body_part_tag_present = '1'"))
    vocab_payers = set(q(f"select payer_id from read_csv('{w}/vocab_payers.csv', header=true, all_varchar=true)"))
    used_payers = set(q(f"select distinct payer_id from read_csv('{w}/coverage.csv', header=true, all_varchar=true)"))
    con.close()
    return {
        "procedures_all_occur": vocab_cpt <= used_cpt,
        "procedures_all_in_vocabulary": used_cpt <= vocab_cpt,
        "body_parts_in_vocabulary": used_terms <= terms,
        "payers_all_occur": vocab_payers <= used_payers,
    }


def run(wh: Path, duckdb_path: Path) -> AuditResult:
    wh = Path(wh).resolve()
    duckdb_path = Path(duckdb_path).resolve()
    _stage_vocab(wh)
    controls = vocabulary_controls(wh)
    if duckdb_path.exists():
        duckdb_path.unlink()
    env = {**os.environ, "IFA_WAREHOUSE": wh.as_posix(), "IFA_DUCKDB": duckdb_path.as_posix()}
    proc = subprocess.run(
        [_dbt_executable(), "build", "--profiles-dir", str(DBT_DIR), "--project-dir", str(DBT_DIR), "--no-use-colors", "--quiet"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(DBT_DIR),
    )
    log = proc.stdout + proc.stderr
    if proc.returncode not in (0,):
        # dbt exits 1 when a test fails at severity error; ours are warn, so 1 means a real problem.
        raise RuntimeError(f"dbt build failed (exit {proc.returncode}):\n{log[-4000:]}")
    con = duckdb.connect(str(duckdb_path), read_only=True)
    flags: dict[str, int] = {}
    tables = {r[0] for r in con.execute(f"select table_name from information_schema.tables where table_schema = '{FAILURE_SCHEMA}'").fetchall()}
    for rule, test in RULE_TEST.items():
        if test in tables:
            flags[rule] = con.execute(f'select count(*) from "{FAILURE_SCHEMA}"."{test}"').fetchone()[0]
        else:
            flags[rule] = 0
    con.close()
    return AuditResult(flags=flags, vocab_controls=controls, dbt_log=log)


def wilson(caught: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = caught / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _flagged_keys(con, rule: str, study_to_accession: dict[str, str]) -> set[str]:
    test = RULE_TEST[rule]
    tables = {r[0] for r in con.execute(f"select table_name from information_schema.tables where table_schema = '{FAILURE_SCHEMA}'").fetchall()}
    if test not in tables:
        return set()
    keys = {r[0] for r in con.execute(f'select record_key from "{FAILURE_SCHEMA}"."{test}"').fetchall()}
    if rule in STUDY_KEYED:
        return {study_to_accession.get(k, k) for k in keys}
    return keys


def score(duckdb_path: Path, truth_csv: Path, wh: Path, out_md: Path) -> dict:
    with Path(truth_csv).open(newline="", encoding="utf-8") as f:
        truth = list(csv.DictReader(f))
    con = duckdb.connect(str(duckdb_path), read_only=True)
    study_to_accession = {
        r[0]: r[1] for r in con.execute(f"select study_uid, accession from read_csv('{Path(wh).as_posix()}/orders.csv', header=true, all_varchar=true)").fetchall()
    }
    # Claim-line-keyed flags are mapped to their exam so a cascade recorded on an
    # accession (E01 `other_same_day_accession`) explains an E11 flag on the claim.
    line_to_accession = {
        r[0]: r[1] for r in con.execute(f"select claim_line_id, accession from read_csv('{Path(wh).as_posix()}/claim_lines.csv', header=true, all_varchar=true)").fetchall()
        if r[1]
    }
    direct = [t for t in truth if t["hop"] != "cascade"]
    cascade_rows = [t for t in truth if t["hop"] == "cascade"]
    planted_anywhere = {t["record_key"] for t in direct}
    cascade_by_rule: dict[str, set[str]] = {}
    for t in cascade_rows:
        cascade_by_rule.setdefault(t["error_id"], set()).add(t["record_key"])
    cascade_any = {t["record_key"] for t in cascade_rows}

    def explain(key: str, rule: str) -> str:
        if key in cascade_by_rule.get(rule, set()):
            return "cascade"
        if key in planted_anywhere or line_to_accession.get(key) in planted_anywhere:
            return "cross"  # the record, or the exam a claim line bills, was planted with another error
        if key in cascade_any or line_to_accession.get(key) in cascade_any:
            return "cascade"
        return "unexplained"

    report: dict = {"types": {}, "note": "These numbers measure the rules on synthetic data with known planted errors. They are not results from any client."}
    lines = [
        "# Recall per error type", "", report["note"], "",
        "Recall is caught ÷ planted over the core variants. Hold-out variants were written after the rules were frozen and are scored apart.", "",
    ]
    lines += [
        "| rule | planted | caught | recall | 95% interval | hold-out planted | hold-out caught | cascade flags | cross-flags on other plants | unexplained flags |",
        "|---|---:|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for rule in RULES:
        flagged = _flagged_keys(con, rule, study_to_accession)
        rows = [t for t in direct if t["error_id"] == rule]
        core = [t for t in rows if t["holdout"] != "1"]
        hold = [t for t in rows if t["holdout"] == "1"]
        caught_core = sum(1 for t in core if t["record_key"] in flagged)
        caught_hold = sum(1 for t in hold if t["record_key"] in flagged)
        recall = caught_core / len(core) if core else 0.0
        lo, hi = wilson(caught_core, len(core))
        variants: dict[str, dict] = {}
        for t in rows:
            v = variants.setdefault(t["variant"], {"planted": 0, "caught": 0, "holdout": t["holdout"] == "1"})
            v["planted"] += 1
            v["caught"] += 1 if t["record_key"] in flagged else 0
        for v in variants.values():
            v["recall"] = v["caught"] / v["planted"] if v["planted"] else 0.0
        planted_keys = {t["record_key"] for t in rows}
        extra = flagged - planted_keys
        kinds = {"cascade": 0, "cross": 0, "unexplained": 0}
        for k in extra:
            kinds[explain(k, rule)] += 1
        report["types"][rule] = {
            "planted": len(core), "caught": caught_core, "recall": recall, "recall_non_holdout": recall,
            "holdout_planted": len(hold), "holdout_caught": caught_hold,
            "wilson_low": lo, "wilson_high": hi, "flagged": len(flagged),
            "flags_cascade": kinds["cascade"], "flags_cross": kinds["cross"], "flags_unexplained": kinds["unexplained"],
            "flags_not_planted": len(extra),
            "variants": variants,
        }
        interval = f"{lo:.2f} to {hi:.2f}" if core else "-"
        lines.append(
            f"| {rule} | {len(core)} | {caught_core} | {recall:.2f} | {interval} | {len(hold)} | {caught_hold} | "
            f"{kinds['cascade']} | {kinds['cross']} | {kinds['unexplained']} |"
        )
    lines += ["", "## Per variant", "", "| rule | variant | hold-out | planted | caught | recall |", "|---|---|---|---:|---:|---:|"]
    for rule in RULES:
        for name, v in report["types"][rule]["variants"].items():
            lines.append(f"| {rule} | {name} | {'yes' if v['holdout'] else ''} | {v['planted']} | {v['caught']} | {v['recall']:.2f} |")
    lines += [
        "",
        "Recall = caught ÷ planted over the core variants of each rule; the interval is Wilson, 95%. "
        "A **cascade flag** is on a record the plant was expected to reach without being the planted record: "
        "the patient's other claim lines after a coverage or member-ID change, the other lines of a claim sent to the wrong payer, "
        "the exam that gained an image (docs/error-catalog.md). "
        "A **cross-flag** is on a record planted with a different error. "
        "An **unexplained flag** is a false positive or a mechanism nobody has written down; the target is zero.",
    ]
    con.close()
    Path(out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
