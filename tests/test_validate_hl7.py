"""The HL7 validators, and the proof that each one can see.

Two validators, because of a measured hl7apy limitation (see src/flow/er7.py):

- v2.8 messages are validated with HAPI HL7v2 2.6.0 (Java), through
  `flow.validate_hl7.hapi_validate`. HAPI's structures for v2.8 are on its
  classpath, and it keeps withdrawn fields in position.
- v2.5.1 messages are also parsed with hl7apy in STRICT mode.

Each validator has a positive control in this file: a deliberately malformed
message must FAIL. A validator that passes everything is worthless, and it
would pass silently.
"""
import shutil
from pathlib import Path

import pytest

from flow import er7, validate_hl7

ROOT = Path(__file__).resolve().parents[1]
HAVE_HAPI = validate_hl7.hapi_available()

GOOD_V28 = (
    "MSH|^~\\&|RIS|HARBORLINE|PACS|HARBORLINE|20261101120000||ADT^A04^ADT_A01|MSG0001|P|2.8\r"
    "EVN||20261101120000\r"
    "PID|1||MRN0001^^^HARBORLINE^MR||ASHFORD^AVERY||19420305|F\r"
    "PV1||N\r"
)
BAD_V28 = GOOD_V28.replace("EVN||20261101120000", "EVN||2026-11-01 noon")

GOOD_V251 = (
    "MSH|^~\\&|RIS|HARBORLINE|PACS|HARBORLINE|20261101120000||ADT^A04^ADT_A01|MSG0001|P|2.5.1\r"
    "EVN|A04|20261101120000\r"
    "PID|1||MRN0001^^^HARBORLINE^MR||ASHFORD^AVERY||19420305|F\r"
    "PV1||N\r"
)
BAD_V251 = GOOD_V251.replace("PV1||N", "PV1||N||||||||||||||||||||||||||||||||||||||||||||||||||||||||ZZZ")


@pytest.mark.skipif(not HAVE_HAPI, reason="HAPI jars or a JDK are missing (see tools/hl7-validate/README.md)")
def test_hapi_accepts_a_correct_v28_message(tmp_path):
    f = tmp_path / "good.hl7"
    f.write_bytes(GOOD_V28.encode())
    results = validate_hl7.hapi_validate([f])
    assert results[0].ok and results[0].structure == "ADT_A01" and results[0].version == "2.8"


@pytest.mark.skipif(not HAVE_HAPI, reason="HAPI jars or a JDK are missing")
def test_control_hapi_rejects_a_malformed_v28_datetime(tmp_path):
    f = tmp_path / "bad.hl7"
    f.write_bytes(BAD_V28.encode())
    results = validate_hl7.hapi_validate([f])
    assert results[0].ok is False and "EVN-2" in results[0].detail


def test_hl7apy_strict_accepts_a_correct_v251_message():
    assert validate_hl7.hl7apy_strict(GOOD_V251).ok


def test_control_hl7apy_strict_rejects_an_overlong_v251_segment():
    assert validate_hl7.hl7apy_strict(BAD_V251).ok is False


def test_hl7apy_is_not_used_for_v28_because_its_positions_are_wrong():
    # The measured defect this repo works around: hl7apy writes v2.8 OBR-16 in
    # position 14. If a future hl7apy fixes this, the test fails and the v2.8
    # path can be reconsidered.
    from hl7apy.core import Segment
    from hl7apy.consts import VALIDATION_LEVEL

    obr = Segment("OBR", version="2.8", validation_level=VALIDATION_LEVEL.TOLERANT)
    obr.obr_16 = "1234567893^ASHFORD^AVERY"
    parts = obr.to_er7().split("|")
    assert parts[14] == "1234567893^ASHFORD^AVERY", "hl7apy now places OBR-16 correctly; revisit validate_hl7"
    ours = er7.Segment("OBR", version="2.8")
    ours.set(16, "1234567893^ASHFORD^AVERY")
    assert ours.to_er7().split("|")[16] == "1234567893^ASHFORD^AVERY"
