#!/usr/bin/env bash
# Fetch the pinned HAPI HL7v2 jars (ca.uhn.hapi 2.6.0, MPL/GPL dual licence) and
# the slf4j jars they log through, into downloads/hapi/, and verify every
# SHA-256 against SHA256SUMS beside this script. Then compile the validator.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p downloads/hapi
V=2.6.0; S=1.7.36
for a in hapi-base hapi-structures-v28 hapi-structures-v281 hapi-structures-v251; do
  [ -f "downloads/hapi/$a-$V.jar" ] || curl -sS -L -o "downloads/hapi/$a-$V.jar" "https://repo1.maven.org/maven2/ca/uhn/hapi/$a/$V/$a-$V.jar"
done
for a in slf4j-api slf4j-simple; do
  [ -f "downloads/hapi/$a-$S.jar" ] || curl -sS -L -o "downloads/hapi/$a-$S.jar" "https://repo1.maven.org/maven2/org/slf4j/$a/$S/$a-$S.jar"
done
(cd downloads/hapi && sha256sum -c ../../tools/hl7-validate/SHA256SUMS)
mkdir -p tools/hl7-validate/out
javac -cp "downloads/hapi/*" -d tools/hl7-validate/out tools/hl7-validate/Validate.java
echo "HAPI validator ready"
