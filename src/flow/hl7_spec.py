"""HL7 v2 structure and field metadata, read from hl7apy's tables.

hl7apy generates its tables from the HL7 standard's database, so a field's
data type, long name, optionality and repeat rule here are the standard's for
that version, not something written from memory. Two things to know:

- A field's NUMBER is carried in its hl7apy name (``OBR_16`` is OBR-16). Its
  position in hl7apy's child list is not the number, because withdrawn fields
  are dropped from the list (in v2.8 EVN-1 is withdrawn, so the first EVN
  child is ``EVN_2``). Everything here keys on the number in the name.
- A withdrawn field appears with data type ``WD`` and cardinality (0, 0).

Message structures: an event may use another event's structure (ADT^A04 uses
ADT_A01). The mapping below is the standard's message-structure table for the
events this flow sends; `structure_for` refuses a pair the version no longer
defines (ORM^O01 is not in v2.8).
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import lru_cache

# Event -> message structure, per the HL7 v2.x message definition tables.
_STRUCTURE_FOR_EVENT = {
    ("ADT", "A01"): "ADT_A01",
    ("ADT", "A04"): "ADT_A01",
    ("ADT", "A08"): "ADT_A01",
    ("OMI", "O23"): "OMI_O23",
    ("OMG", "O19"): "OMG_O19",
    ("ORM", "O01"): "ORM_O01",
    ("ORU", "R01"): "ORU_R01",
}


@dataclass(frozen=True)
class FieldInfo:
    version: str
    segment: str
    number: int
    name: str
    datatype: str
    long_name: str
    table: str | None
    min_occurs: int
    max_occurs: int  # -1 means unbounded

    @property
    def required(self) -> bool:
        return self.min_occurs >= 1

    @property
    def repeats(self) -> bool:
        return self.max_occurs == -1 or self.max_occurs > 1

    @property
    def withdrawn(self) -> bool:
        return self.datatype == "WD" or (self.min_occurs, self.max_occurs) == (0, 0)


@lru_cache(maxsize=None)
def _tables(version: str):
    return importlib.import_module("hl7apy.v" + version.replace(".", "_"))


def segment_fields(version: str, segment: str) -> list[FieldInfo]:
    mod = _tables(version)
    if segment not in mod.SEGMENTS:
        raise KeyError(f"{segment} is not a segment in v{version}")
    out: list[FieldInfo] = []
    for child in mod.SEGMENTS[segment][1]:
        fname, dfn, (lo, hi), _kind = child
        number = int(fname.split("_", 1)[1])
        datatype = dfn[2] or "varies"
        out.append(FieldInfo(version, segment, number, fname, datatype, dfn[3] or "", dfn[4], lo, hi))
    return out


def field_info(version: str, segment: str, number: int) -> FieldInfo:
    fields = segment_fields(version, segment)
    for f in fields:
        if f.number == number:
            return f
    # hl7apy drops some withdrawn fields from its list instead of marking them
    # WD (v2.8 EVN-1, OBR-14, OBR-15, OBR-27, IN1-38, PID-28). A number missing
    # INSIDE the segment's numbering is one of those; beyond the last number it
    # is undefined.
    if fields and 1 <= number < max(f.number for f in fields):
        return FieldInfo(version, segment, number, f"{segment}_{number}", "WD", "WITHDRAWN", None, 0, 0)
    raise KeyError(f"{segment}-{number} is not defined in v{version}")


def message_segments(version: str, structure: str) -> list[str]:
    """Segment names in document order, groups flattened, repeats kept."""
    mod = _tables(version)
    if structure not in mod.MESSAGES:
        raise KeyError(f"{structure} is not a message structure in v{version}")
    names: list[str] = []

    def walk(seq) -> None:
        for child in seq[1]:
            name, dfn, _card, kind = child
            if kind == "GRP":
                walk(dfn)
            else:
                names.append(name)

    walk(mod.MESSAGES[structure])
    return names


def structure_for(version: str, message_code: str, trigger_event: str) -> str:
    structure = _STRUCTURE_FOR_EVENT.get((message_code, trigger_event))
    if structure is None:
        raise KeyError(f"no structure mapping for {message_code}^{trigger_event}")
    if structure not in _tables(version).MESSAGES:
        raise KeyError(f"{message_code}^{trigger_event} ({structure}) is not defined in v{version}")
    return structure
