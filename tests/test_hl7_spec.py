"""The HL7 field metadata the generators and the field notes rely on.

hl7apy's tables are generated from the HL7 standard's own database. A field's
NUMBER is carried in its name (OBR_16 is OBR-16) and not by its position in
hl7apy's list, because withdrawn fields are dropped from that list: in v2.8,
EVN-1 is withdrawn, so hl7apy's first EVN child is EVN_2. These tests pin that
mapping, so the notes cannot drift off the standard's numbering.
"""
import pytest

from flow import hl7_spec


def test_field_number_comes_from_the_name_not_the_list_position():
    f = hl7_spec.field_info("2.8", "OBR", 16)
    assert f.long_name == "ORDERING_PROVIDER"
    assert f.datatype == "XCN"


def test_withdrawn_field_is_reported_as_withdrawn():
    f = hl7_spec.field_info("2.8", "PID", 2)
    assert f.withdrawn is True


def test_a_required_repeating_field():
    f = hl7_spec.field_info("2.8", "PID", 3)
    assert f.required is True and f.repeats is True and f.datatype == "CX"


def test_datatypes_differ_between_versions_where_the_standard_changed_them():
    assert hl7_spec.field_info("2.8", "PID", 8).datatype == "CWE"
    assert hl7_spec.field_info("2.5.1", "PID", 8).datatype == "IS"
    assert hl7_spec.field_info("2.8", "MSH", 7).datatype == "DTM"
    assert hl7_spec.field_info("2.5.1", "MSH", 7).datatype == "TS"


def test_ipc_segment_fields_in_v28():
    f = hl7_spec.field_info("2.8", "IPC", 1)
    assert f.long_name == "ACCESSION_IDENTIFIER" and f.required is True


def test_unknown_field_number_raises():
    with pytest.raises(KeyError):
        hl7_spec.field_info("2.8", "IPC", 40)


def test_message_structure_lists_segments_in_order():
    segs = hl7_spec.message_segments("2.8", "OMI_O23")
    assert segs[:3] == ["MSH", "SFT", "UAC"]
    assert "IPC" in segs and "ORC" in segs


def test_structure_name_for_event():
    # ADT^A04 uses the ADT_A01 structure in every version.
    assert hl7_spec.structure_for("2.8", "ADT", "A04") == "ADT_A01"
    assert hl7_spec.structure_for("2.8", "OMI", "O23") == "OMI_O23"
    assert hl7_spec.structure_for("2.5.1", "ORM", "O01") == "ORM_O01"
    with pytest.raises(KeyError):
        hl7_spec.structure_for("2.8", "ORM", "O01")


def test_a_field_hl7apy_omits_inside_the_numbering_is_withdrawn_not_undefined():
    # v2.8 withdrew EVN-1; hl7apy drops it from its list rather than marking it WD.
    f = hl7_spec.field_info("2.8", "EVN", 1)
    assert f.withdrawn is True
    # Beyond the segment's last field number is undefined, not withdrawn.
    with pytest.raises(KeyError):
        hl7_spec.field_info("2.8", "EVN", 8)
