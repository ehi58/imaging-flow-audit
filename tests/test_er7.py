"""The ER7 encoder places every field at the standard's field number.

Why this exists: hl7apy's v2.8 tables drop withdrawn fields, so it writes
EVN-2 in position 1 and OBR-16 in position 14 (measured 2026-11-01, hl7apy
1.3.5). A message encoded that way is not a v2.8 message. This encoder keys on
the field number from hl7_spec, refuses withdrawn fields, and escapes the
delimiter characters the way HL7 2.x requires.
"""
import pytest

from flow import er7


def test_evn_recorded_time_lands_in_position_2_in_v28():
    seg = er7.Segment("EVN", version="2.8")
    seg.set(2, "20261101120000")
    assert seg.to_er7() == "EVN||20261101120000"


def test_obr_ordering_provider_lands_in_position_16_in_v28():
    seg = er7.Segment("OBR", version="2.8")
    seg.set(4, "71046^XR CHEST 2 VIEWS^C4")
    seg.set(16, "1234567893^ASHFORD^AVERY^^^^^^NPI")
    parts = seg.to_er7().split("|")
    assert parts[0] == "OBR"
    assert parts[4] == "71046^XR CHEST 2 VIEWS^C4"
    assert parts[16] == "1234567893^ASHFORD^AVERY^^^^^^NPI"
    assert len(parts) == 17  # nothing trailing after the last set field


def test_setting_a_withdrawn_field_is_refused():
    seg = er7.Segment("EVN", version="2.8")
    with pytest.raises(er7.WithdrawnField):
        seg.set(1, "A04")
    seg251 = er7.Segment("EVN", version="2.5.1")
    seg251.set(1, "A04")  # EVN-1 still exists in v2.5.1
    assert seg251.to_er7().startswith("EVN|A04")


def test_setting_an_undefined_field_number_is_refused():
    seg = er7.Segment("IPC", version="2.8")
    with pytest.raises(KeyError):
        seg.set(40, "x")


def test_repeating_field_joins_repeats_with_tilde():
    seg = er7.Segment("PID", version="2.8")
    seg.set(3, ["MRN0001^^^HARBORLINE^MR", "ACCT9^^^HARBORLINE^AN"])
    assert seg.to_er7() == "PID|||MRN0001^^^HARBORLINE^MR~ACCT9^^^HARBORLINE^AN"


def test_repeats_on_a_non_repeating_field_are_refused():
    seg = er7.Segment("PID", version="2.8")
    with pytest.raises(er7.NotRepeating):
        seg.set(7, ["19420305", "19420306"])


def test_msh_puts_the_separators_in_fields_1_and_2():
    msh = er7.msh(
        version="2.8",
        sending_app="RIS",
        sending_facility="HARBORLINE",
        receiving_app="PACS",
        receiving_facility="HARBORLINE",
        timestamp="20261101120000",
        message_type="ADT^A04^ADT_A01",
        control_id="MSG0001",
    )
    assert msh.to_er7() == "MSH|^~\\&|RIS|HARBORLINE|PACS|HARBORLINE|20261101120000||ADT^A04^ADT_A01|MSG0001|P|2.8"


def test_text_values_are_escaped():
    assert er7.escape("a|b^c~d\\e&f") == "a\\F\\b\\S\\c\\R\\d\\E\\e\\T\\f"


def test_message_joins_segments_with_carriage_returns():
    msh = er7.msh(version="2.8", sending_app="A", sending_facility="B", receiving_app="C", receiving_facility="D", timestamp="20261101120000", message_type="ADT^A04^ADT_A01", control_id="1")
    evn = er7.Segment("EVN", version="2.8")
    evn.set(2, "20261101120000")
    assert er7.message([msh, evn]) == msh.to_er7() + "\r" + evn.to_er7() + "\r"
