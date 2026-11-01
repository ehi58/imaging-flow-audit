"""A position-correct HL7 v2 ER7 encoder.

Fields are placed by the standard's field NUMBER (from `hl7_spec`, which reads
hl7apy's tables), so a withdrawn field keeps its empty slot. hl7apy's own
serialiser does not do this for v2.8: it drops withdrawn fields from its list
and writes EVN-2 in position 1 and OBR-16 in position 14 (measured with
hl7apy 1.3.5 on 2026-11-01), which is why this module exists. Validation of
the v2.8 output is done with HAPI (tools/hl7-validate); v2.5.1 output is also
parsed with hl7apy in strict mode, whose v2.5.1 tables have no such gap in the
segments this flow uses.
"""
from __future__ import annotations

from flow import hl7_spec

FIELD_SEP = "|"
COMPONENT_SEP = "^"
REPEAT_SEP = "~"
ESCAPE_CHAR = "\\"
SUBCOMPONENT_SEP = "&"
ENCODING_CHARS = COMPONENT_SEP + REPEAT_SEP + ESCAPE_CHAR + SUBCOMPONENT_SEP
SEGMENT_TERMINATOR = "\r"


class WithdrawnField(ValueError):
    pass


class NotRepeating(ValueError):
    pass


def escape(text: str) -> str:
    """Escape the five delimiter characters inside a text value."""
    return (
        text.replace(ESCAPE_CHAR, "\\E\\")
        .replace(FIELD_SEP, "\\F\\")
        .replace(COMPONENT_SEP, "\\S\\")
        .replace(REPEAT_SEP, "\\R\\")
        .replace(SUBCOMPONENT_SEP, "\\T\\")
    )


class Segment:
    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version
        self._fields = {f.number: f for f in hl7_spec.segment_fields(version, name)}
        self._values: dict[int, str] = {}

    def set(self, number: int, value: str | list[str] | None) -> "Segment":
        """Set field `number` to a pre-encoded value (components already joined with ^).

        A list is a repeating field; its items are joined with ~.
        """
        info = self._fields.get(number) or hl7_spec.field_info(self.version, self.name, number)
        if info.withdrawn:
            raise WithdrawnField(f"{self.name}-{number} is withdrawn in v{self.version}")
        if value is None or value == "" or value == []:
            self._values.pop(number, None)
            return self
        if isinstance(value, list):
            if len(value) > 1 and not info.repeats:
                raise NotRepeating(f"{self.name}-{number} does not repeat in v{self.version}")
            encoded = REPEAT_SEP.join(value)
        else:
            encoded = value
        self._values[number] = encoded
        return self

    def get(self, number: int) -> str | None:
        return self._values.get(number)

    def to_er7(self) -> str:
        if not self._values:
            return self.name
        last = max(self._values)
        parts = [self.name] + [self._values.get(i, "") for i in range(1, last + 1)]
        return FIELD_SEP.join(parts)


class _MSH(Segment):
    """MSH is special: field 1 is the separator itself and field 2 the encoding characters."""

    def to_er7(self) -> str:
        last = max(self._values) if self._values else 2
        parts = [self.name, ENCODING_CHARS] + [self._values.get(i, "") for i in range(3, last + 1)]
        return FIELD_SEP.join(parts)


def msh(
    *,
    version: str,
    sending_app: str,
    sending_facility: str,
    receiving_app: str,
    receiving_facility: str,
    timestamp: str,
    message_type: str,
    control_id: str,
    processing_id: str = "P",
) -> Segment:
    seg = _MSH("MSH", version)
    seg.set(3, sending_app)
    seg.set(4, sending_facility)
    seg.set(5, receiving_app)
    seg.set(6, receiving_facility)
    seg.set(7, timestamp)
    seg.set(9, message_type)
    seg.set(10, control_id)
    seg.set(11, processing_id)
    seg.set(12, version)
    return seg


def message(segments: list[Segment]) -> str:
    """Segments joined and terminated by carriage returns, as HL7 v2 requires."""
    return "".join(s.to_er7() + SEGMENT_TERMINATOR for s in segments)
