"""HL7 v2 validation: HAPI (Java) for every version, hl7apy strict for v2.5.1.

See tests/test_validate_hl7.py for why two validators, and tools/hl7-validate/
for the Java side (HAPI HL7v2 2.6.0, structures v2.5.1, v2.8 and v2.8.1).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HAPI_DIR = ROOT / "downloads" / "hapi"
VALIDATOR_OUT = ROOT / "tools" / "hl7-validate" / "out"


@dataclass(frozen=True)
class Result:
    path: Path
    ok: bool
    structure: str | None
    version: str | None
    detail: str


def _java() -> str | None:
    home = os.environ.get("JAVA_HOME")
    if home:
        exe = Path(home) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if exe.exists():
            return str(exe)
    return shutil.which("java")


def hapi_available() -> bool:
    return (
        _java() is not None
        and (VALIDATOR_OUT / "Validate.class").exists()
        and any(HAPI_DIR.glob("hapi-base-*.jar"))
        and any(HAPI_DIR.glob("hapi-structures-v28-*.jar"))
    )


def hapi_validate(paths: list[Path]) -> list[Result]:
    """Run the HAPI validator over files; one Result per file, in order."""
    java = _java()
    if java is None:
        raise RuntimeError("no java on PATH and JAVA_HOME unset")
    classpath = os.pathsep.join([str(HAPI_DIR / "*"), str(VALIDATOR_OUT)])
    # Paths go through a list file: thousands of arguments exceed the Windows
    # command-line limit (WinError 206, measured 2026-11-01).
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as lst:
        lst.write("\n".join(str(p) for p in paths) + "\n")
        list_path = lst.name
    try:
        proc = subprocess.run(
            [java, "-cp", classpath, "Validate", f"@{list_path}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    finally:
        os.unlink(list_path)
    results: list[Result] = []
    by_path = {str(p): p for p in paths}
    for line in proc.stdout.splitlines():
        if line.startswith("OK "):
            _, rest = line.split(" ", 1)
            # "OK <path> <structure> v<version>"
            path_str, structure, version = rest.rsplit(" ", 2)
            results.append(Result(by_path.get(path_str, Path(path_str)), True, structure, version.lstrip("v"), ""))
        elif line.startswith("FAIL "):
            _, rest = line.split(" ", 1)
            path_str, detail = rest.split(" ", 1)
            results.append(Result(by_path.get(path_str, Path(path_str)), False, None, None, detail))
    if len(results) != len(paths):
        raise RuntimeError(f"validator reported {len(results)} of {len(paths)} files; stderr: {proc.stderr[-2000:]}")
    return results


@dataclass(frozen=True)
class StrictResult:
    ok: bool
    detail: str


def hl7apy_strict(er7_text: str) -> StrictResult:
    """Parse with hl7apy in STRICT mode. Sound for v2.5.1; not used for v2.8."""
    from hl7apy.consts import VALIDATION_LEVEL
    from hl7apy.parser import parse_message

    try:
        parse_message(er7_text, validation_level=VALIDATION_LEVEL.STRICT, find_groups=True)
        return StrictResult(True, "")
    except Exception as e:  # hl7apy raises several exception types for structural faults
        return StrictResult(False, f"{type(e).__name__}: {e}")
