"""Small file helpers: CSV with fixed columns and LF endings, HL7 as bytes with
carriage returns intact, and a SHA-256 manifest of everything written.

Hashing happens in memory at write time. Re-reading thousands of just-written
files to hash them cost about 9 ms per file on Windows (real-time scanning on
open; 95 s of a 109 s run, measured 2026-11-01), so no writer re-opens a file.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Iterable

# posix path relative to the run root -> sha256 of the bytes written
_HASHES: dict[str, str] = {}
_ROOT: Path | None = None


def start_manifest(root: Path) -> None:
    global _ROOT
    _ROOT = Path(root).resolve()
    _HASHES.clear()


def write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if _ROOT is not None:
        try:
            key = path.resolve().relative_to(_ROOT).as_posix()
        except ValueError:
            key = path.as_posix()
        _HASHES[key] = hashlib.sha256(data).hexdigest()


def manifest() -> dict[str, str]:
    return dict(sorted(_HASHES.items()))


def write_csv(path: Path, rows: Iterable, columns: list[str]) -> int:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    n = 0
    for r in rows:
        d = asdict(r) if is_dataclass(r) else dict(r)
        for k, v in list(d.items()):
            if isinstance(v, list):
                d[k] = " ".join(v)
            elif v is None:
                d[k] = ""
            elif hasattr(v, "isoformat"):
                d[k] = v.isoformat(sep=" ") if hasattr(v, "hour") else v.isoformat()
        w.writerow(d)
        n += 1
    write_bytes(Path(path), buf.getvalue().encode("utf-8"))
    return n


def write_hl7(path: Path, er7_text: str) -> None:
    write_bytes(Path(path), er7_text.encode("utf-8"))


def write_text(path: Path, text: str) -> None:
    write_bytes(Path(path), text.encode("utf-8"))


def sha256_tree(root: Path, skip: set[str] = frozenset()) -> dict[str, str]:
    """Hash a tree by reading it (slow on Windows; kept for independent checks)."""
    out: dict[str, str] = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and p.name not in skip:
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out
