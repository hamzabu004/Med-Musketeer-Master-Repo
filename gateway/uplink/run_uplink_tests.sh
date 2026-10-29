#!/usr/bin/env bash
set -Eeuo pipefail

# Runs the uplink's unit tests and, with podman and eclipse-mosquitto:2.0.21, TC-B05 to TC-B08,
# and stores the raw evidence. Usage: ./run_uplink_tests.sh [output-dir]
# Default output: docs/testing/evidence/<date>/uplink/

cd "$(dirname "$0")"
readonly REPO_ROOT="$(cd ../.. && pwd)"
readonly OUT="$(mkdir -p "${1:-$REPO_ROOT/docs/testing/evidence/$(date +%F)/uplink}" && cd "${1:-$REPO_ROOT/docs/testing/evidence/$(date +%F)/uplink}" && pwd)"
readonly PYTHON=".venv/bin/python"

{
    printf 'run_at: %s\n' "$(date -Is)"
    printf 'host: %s\n' "$(uname -srm)"
    printf 'python: %s\n' "$("$PYTHON" --version 2>&1)"
    printf 'packages: %s\n' "$("$PYTHON" -m pip freeze 2>/dev/null | grep -Ei '^(paho-mqtt|jsonschema|cryptography|pytest)==' | tr '\n' ' ')"
    printf 'podman: %s\n' "$(podman --version 2>&1 || echo missing)"
    printf 'image: %s\n' "$(podman image inspect --format '{{.Id}}' docker.io/library/eclipse-mosquitto:2.0.21 2>&1 || echo missing)"
    printf 'commit: %s\n' "$(git -C "$REPO_ROOT" rev-parse HEAD)"
    printf 'uncommitted changes:\n%s\n' "$(git -C "$REPO_ROOT" status --short)"
} > "$OUT/environment.txt"

set +e
MM_EVIDENCE_DIR="$OUT/broker" "$PYTHON" -m pytest -rA -p no:cacheprovider --junitxml="$OUT/junit.xml" 2>&1 \
    | tee "$OUT/pytest.txt"
status=${PIPESTATUS[0]}
set -e

printf '\nEvidence written to %s (pytest exit %s)\n' "$OUT" "$status"
exit "$status"
