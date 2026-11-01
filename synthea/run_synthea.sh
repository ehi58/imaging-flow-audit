#!/usr/bin/env bash
# Regenerate the Synthea population. Run from the repository root.
#   synthea/run_synthea.sh [population] [seed]
# The jar is Synthea v4.0.0 (Apache-2.0), downloaded to downloads/synthea/ by
# synthea/fetch_jar.sh; its SHA-256 is pinned there. Needs a JDK 17 or later.
set -euo pipefail
POP="${1:-2000}"
SEED="${2:-20261101}"
JAR="downloads/synthea/synthea-with-dependencies.jar"
JAVA="${JAVA:-java}"
[ -f "$JAR" ] || { echo "missing $JAR; run synthea/fetch_jar.sh" >&2; exit 2; }
rm -rf synthea/output
# -a 65-100: nursing-facility residents. -s seed, -cs clinician seed, -r reference date.
"$JAVA" -jar "$JAR" -c config/synthea/synthea.properties -p "$POP" -s "$SEED" -cs "$SEED" -r 20261101 -a 65-100 "New Jersey"
ls -la synthea/output/csv
