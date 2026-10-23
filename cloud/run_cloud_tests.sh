#!/usr/bin/env bash
set -Eeuo pipefail

# Runs the cloud backend tests (unit and, with Docker, the compose-stack integration tests) and
# stores the raw evidence. Usage: ./run_cloud_tests.sh [output-dir]
# Default output: docs/testing/evidence/<date>/cloud/

readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Resolve the output directory before changing directory, so a relative path means the caller's.
readonly OUT="$(mkdir -p "${1:-$REPO_ROOT/docs/testing/evidence/$(date +%F)/cloud}" && cd "${1:-$REPO_ROOT/docs/testing/evidence/$(date +%F)/cloud}" && pwd)"
cd "$SCRIPT_DIR/backend"
readonly PYTHON=".venv/bin/python"
readonly COMPOSE="${MM_COMPOSE:-docker compose}"
readonly ENGINE="${COMPOSE%% *}"

{
    printf 'run_at: %s\n' "$(date -Is)"
    printf 'host: %s\n' "$(uname -srm)"
    printf 'python: %s\n' "$("$PYTHON" --version 2>&1)"
    printf 'packages: %s\n' "$("$PYTHON" -m pip freeze 2>/dev/null | grep -Ei '^(fastapi|sqlalchemy|psycopg|pydantic-settings|httpx|pytest|pytest-cov)==' | tr '\n' ' ')"
    printf 'compose: %s\n' "$($COMPOSE version 2>&1 | head -1 || echo missing)"
    printf 'engine: %s %s\n' "$ENGINE" "$("$ENGINE" version --format '{{.Server.Version}}' 2>&1 || echo missing)"
    printf 'images: %s\n' "$(grep -E '^\s+image:' ../compose.yaml | awk '{print $2}' | tr '\n' ' ')"
    printf 'commit: %s\n' "$(git -C "$REPO_ROOT" rev-parse HEAD)"
    printf 'uncommitted changes:\n%s\n' "$(git -C "$REPO_ROOT" status --short)"
} > "$OUT/environment.txt"

coverage=()
if "$PYTHON" -c 'import pytest_cov' 2>/dev/null; then
    coverage=(--cov=app --cov-branch --cov-report=term-missing --cov-report="xml:$OUT/coverage.xml")
fi

set +e
MM_EVIDENCE_DIR="$OUT/stack" "$PYTHON" -m pytest -rA -p no:cacheprovider \
    --junitxml="$OUT/junit.xml" "${coverage[@]}" 2>&1 | tee "$OUT/pytest.txt"
status=${PIPESTATUS[0]}
set -e

printf '\nEvidence written to %s (pytest exit %s)\n' "$OUT" "$status"
exit "$status"
