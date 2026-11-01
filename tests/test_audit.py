"""The audit: dbt on DuckDB over the extracted warehouse, then the scorer.

Controls, as the plan requires:
- the clean run gives zero flags (or a documented baseline), so a rule that
  fires on good data is a defect, not a finding;
- on the injected run every rule fires at least once;
- recall is reported per error type and per variant, hold-outs separately.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from flow import audit, pipeline

WINDOW = (date(2025, 1, 1), date(2025, 2, 28))


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    out = tmp_path_factory.mktemp("clean")
    pipeline.generate(seed=91, window=WINDOW, out_dir=out, inject=False, validate=False)
    wh = pipeline.extract(out)
    return out, audit.run(wh, out / "audit.duckdb")


@pytest.fixture(scope="module")
def injected(tmp_path_factory):
    out = tmp_path_factory.mktemp("inj")
    pipeline.generate(seed=91, window=WINDOW, out_dir=out, inject=True, validate=False)
    wh = pipeline.extract(out)
    result = audit.run(wh, out / "audit.duckdb")
    report = audit.score(out / "audit.duckdb", out / "truth" / "planted_errors.csv", wh, out / "recall.md")
    return out, result, report


def test_vocabulary_controls_pass_on_the_clean_run(clean):
    _, result = clean
    assert result.vocab_controls["procedures_all_occur"] is True
    assert result.vocab_controls["body_parts_in_vocabulary"] is True
    assert result.vocab_controls["payers_all_occur"] is True


def test_every_rule_exists_and_the_clean_run_flags_nothing(clean):
    _, result = clean
    assert set(result.flags) == set(audit.RULES)
    assert {k: v for k, v in result.flags.items() if v} == {}, result.flags


def test_every_rule_fires_on_the_injected_run(injected):
    _, result, _ = injected
    silent = [r for r, n in result.flags.items() if n == 0]
    assert silent == [], silent


def test_recall_is_reported_per_type_and_variant_with_holdouts_apart(injected):
    _, _, report = injected
    for eid in audit.RULES:
        row = report["types"][eid]
        assert row["planted"] > 0 and 0.0 <= row["recall"] <= 1.0
        assert "wilson_low" in row and "wilson_high" in row
        assert row["variants"] and all("holdout" in v for v in row["variants"].values())
        assert any(v["holdout"] for v in row["variants"].values())


def test_core_variants_are_mostly_caught(injected):
    _, _, report = injected
    weak = {eid: r["recall_non_holdout"] for eid, r in report["types"].items() if r["recall_non_holdout"] < 0.9}
    assert weak == {}, weak


def test_recall_markdown_is_written_with_the_denominators(injected):
    out, _, report = injected
    text = (out / "recall.md").read_text(encoding="utf-8")
    assert "planted" in text and "caught" in text and "hold-out" in text.lower()
    for eid in audit.RULES:
        assert eid in text
    assert "synthetic" in text.lower()
