"""Shared test setup. If JAVA_HOME is unset, look in the usual places so the
HAPI-backed tests run locally without a shell variable; CI sets JAVA_HOME."""
import glob
import os

if not os.environ.get("JAVA_HOME"):
    for pattern in (
        r"C:\Program Files\Eclipse Adoptium\jdk-*",
        "/usr/lib/jvm/temurin-*",
        "/usr/lib/jvm/java-*",
        "/opt/homebrew/opt/openjdk*",
    ):
        hits = sorted(glob.glob(pattern))
        if hits:
            os.environ["JAVA_HOME"] = hits[-1]
            break
