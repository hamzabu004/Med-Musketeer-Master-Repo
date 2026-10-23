#!/usr/bin/env bash
set -Eeuo pipefail

# Runs the CA-tool, secret-scan, and broker interop tests and stores the raw evidence that the
# report's test tables cite. Usage: ./run_report_tests.sh [output-dir]

cd "$(dirname "$0")"
readonly REPO_ROOT="$(cd ../.. && pwd)"
readonly OUT="$(mkdir -p "${1:-$REPO_ROOT/docs/testing/evidence/$(date +%F)}" && cd "${1:-$REPO_ROOT/docs/testing/evidence/$(date +%F)}" && pwd)"
readonly PYTHON=".venv/bin/python"

{
    printf 'run_at: %s\n' "$(date -Is)"
    printf 'host: %s\n' "$(uname -srm)"
    printf 'python: %s\n' "$("$PYTHON" --version 2>&1)"
    printf 'packages: %s\n' "$("$PYTHON" -m pip freeze 2>/dev/null | grep -Ei '^(cryptography|paramiko|esptool|pytest|pytest-cov)==' | tr '\n' ' ')"
    printf 'openssl: %s\n' "$(openssl version 2>&1 || echo missing)"
    printf 'podman: %s\n' "$(podman --version 2>&1 || echo missing)"
    printf 'commit: %s\n' "$(git -C "$REPO_ROOT" rev-parse HEAD)"
    printf 'uncommitted changes:\n%s\n' "$(git -C "$REPO_ROOT" status --short)"
} > "$OUT/environment.txt"

coverage=()
if "$PYTHON" -c 'import pytest_cov' 2>/dev/null; then
    coverage=(--cov=mmca --cov-branch --cov-report=term-missing --cov-report="xml:$OUT/coverage.xml")
fi

set +e
MM_EVIDENCE_DIR="$OUT/broker" "$PYTHON" -m pytest -rA -p no:cacheprovider \
    --junitxml="$OUT/junit.xml" "${coverage[@]}" 2>&1 | tee "$OUT/pytest.txt"
status=${PIPESTATUS[0]}
set -e

printf '\nEvidence written to %s (pytest exit %s)\n' "$OUT" "$status"
exit "$status"
