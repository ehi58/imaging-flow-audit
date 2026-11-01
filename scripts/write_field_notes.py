"""Write docs/hl7-field-notes.md and the six sample messages under data/samples/.

    .venv/Scripts/python scripts/write_field_notes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flow import field_notes  # noqa: E402

FILES = {
    "ADT^A04 (v2.8, structure ADT_A01)": "adt_a04_v2.8.hl7",
    "ADT^A04 (v2.5.1)": "adt_a04_v2.5.1.hl7",
    "OMI^O23 imaging order (v2.8)": "omi_o23_v2.8.hl7",
    "ORM^O01 order (v2.5.1, the form most RIS/PACS interfaces still send)": "orm_o01_v2.5.1.hl7",
    "ORU^R01 report (v2.8)": "oru_r01_v2.8.hl7",
    "ORU^R01 report (v2.5.1)": "oru_r01_v2.5.1.hl7",
}


def main() -> None:
    (ROOT / "docs" / "hl7-field-notes.md").write_text(field_notes.render(), encoding="utf-8", newline="\n")
    samples_dir = ROOT / "data" / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    for name, (_version, er7) in field_notes.samples().items():
        (samples_dir / FILES[name]).write_bytes(er7.encode("utf-8"))
    print("wrote docs/hl7-field-notes.md and", len(FILES), "samples")


if __name__ == "__main__":
    main()
