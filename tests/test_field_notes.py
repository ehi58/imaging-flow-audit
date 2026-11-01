"""docs/hl7-field-notes.md is generated from the builders' FIELDS_USED table and
hl7_spec, so it cannot name a field the messages do not carry or misstate a
data type the standard gives. These tests pin that: every used field appears
with its data type and optionality, every sample message is embedded, and the
two forms are told apart.
"""
import re
from pathlib import Path

from flow import field_notes, hl7_messages, hl7_spec

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "hl7-field-notes.md"


def test_generator_writes_the_doc_and_it_is_committed_up_to_date(tmp_path):
    fresh = field_notes.render()
    assert DOC.exists(), "run scripts/write_field_notes.py"
    assert DOC.read_text(encoding="utf-8") == fresh, "docs/hl7-field-notes.md is stale: run scripts/write_field_notes.py"


def test_every_used_field_is_documented_with_its_standard_metadata():
    text = field_notes.render()
    for (version, segment, number), use in hl7_messages.FIELDS_USED.items():
        info = hl7_spec.field_info(version, segment, number)
        row = re.search(rf"^\| {segment}-{number} \| .*$", text, re.M)
        assert row, (version, segment, number)
        cell = row.group(0)
        assert info.datatype in cell, (version, segment, number, info.datatype)
        word = "required" if info.required else "optional"
        # One phrase when every version agrees; a versioned phrase when they differ (OBX-2 is required in v2.8, optional in v2.5.1).
        assert (f"| {word}" in cell) or (f"| {word}, repeats" in cell) or (f"{word} (v{version})" in cell) or (f"{word}, repeats (v{version})" in cell), (version, segment, number, cell)


def test_each_message_form_has_a_sample_and_a_version_note():
    text = field_notes.render()
    for heading in ("ADT^A04", "OMI^O23", "ORM^O01", "ORU^R01"):
        assert heading in text
    assert "v2.8" in text and "v2.5.1" in text
    assert "MSH|^~\\&|" in text
    assert text.count("```") >= 12  # six samples, fenced


def test_the_notes_say_why_each_field_matters():
    text = field_notes.render()
    assert "E01" in text and "E08" in text and "42 CFR 486.106" in text
