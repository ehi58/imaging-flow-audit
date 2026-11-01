# hl7-validate

A thin command-line wrapper around HAPI HL7v2 (`ca.uhn.hapi` 2.6.0) that parses
ER7 files in non-lenient mode with HAPI's default validation context, so a
wrong segment order, a missing required segment, a malformed date/time or an
out-of-table value fails. Structures on the classpath: v2.5.1, v2.8, v2.8.1.

    tools/hl7-validate/fetch_hapi.sh      # downloads the pinned jars, checks SHA-256, compiles
    java -cp "downloads/hapi/*:tools/hl7-validate/out" Validate data/samples/*.hl7

Why HAPI and not hl7apy for v2.8: hl7apy 1.3.5 drops withdrawn fields from its
v2.8 tables and so writes EVN-2 in position 1 and OBR-16 in position 14
(measured 2026-11-01; `tests/test_validate_hl7.py` keeps the measurement).
HAPI keeps withdrawn fields in position. hl7apy's strict parser is still used
for the v2.5.1 messages, where the segments this flow uses have no such gap.

Positive control: `tests/test_validate_hl7.py` feeds the validator a message
whose EVN-2 is not a date/time and requires the failure to name EVN-2.

Licence note: HAPI is MPL 1.1 / GPL dual-licensed and is downloaded at build
time, never vendored. The jars live under `downloads/`, which is gitignored.
