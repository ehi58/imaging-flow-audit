#!/usr/bin/env bash
# Fetch the pinned Synthea release jar and verify its SHA-256.
set -euo pipefail
mkdir -p downloads/synthea
URL="https://github.com/synthetichealth/synthea/releases/download/v4.0.0/synthea-with-dependencies.jar"
SHA="ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1"
OUT="downloads/synthea/synthea-with-dependencies.jar"
[ -f "$OUT" ] || curl -sS -L -o "$OUT" "$URL"
echo "$SHA *$OUT" | sha256sum -c -
