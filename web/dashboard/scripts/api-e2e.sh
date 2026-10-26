#!/usr/bin/env bash
set -Eeuo pipefail

# Browser tests in API mode against a real cloud stack: brings up the compose stack under its own
# project name and ports (a running development stack is not touched), seeds it with seed-dev,
# runs playwright.api.config.mts (sign-in through ZITADEL's login for each role), and removes the
# stack with its volumes. KEEP_STACK=1 leaves it running for a look around.
# Usage: scripts/api-e2e.sh [playwright arguments]

readonly DASHBOARD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
readonly CLOUD_DIR="$(cd "$DASHBOARD_DIR/../../cloud" && pwd)"
readonly PROJECT=mm-dashboard-e2e
readonly DASHBOARD_PORT=3101
readonly API_PORT=18100
readonly WORK="$(mktemp -d)"
read -r -a COMPOSE <<< "${MM_COMPOSE:-docker compose}"

compose() { "${COMPOSE[@]}" -p "$PROJECT" --env-file "$WORK/e2e.env" "$@"; }

cleanup() {
    if [[ "${KEEP_STACK:-0}" == 1 ]]; then
        echo "api-e2e: stack left running (project $PROJECT, env $WORK/e2e.env)" >&2
    else
        compose down --volumes --remove-orphans >/dev/null 2>&1 || true
        rm -rf "$WORK"
    fi
}
trap cleanup EXIT

"$CLOUD_DIR/scripts/init-env.sh" "$WORK/e2e.env" >/dev/null
cat >> "$WORK/e2e.env" <<ENV
PROXY_HTTP_PUBLISHED_PORT=18180
API_PUBLISHED_PORT=$API_PORT
EMQX_DASHBOARD_PUBLISHED_PORT=28183
EMQX_GATEWAY_PUBLISHED_PORT=28983
EMQX_INTERNAL_PUBLISHED_PORT=21983
DASHBOARD_ORIGINS=http://localhost:$DASHBOARD_PORT
ENV

cd "$CLOUD_DIR"
compose down --volumes --remove-orphans >/dev/null 2>&1 || true
echo "api-e2e: starting the cloud stack ($PROJECT)" >&2
compose up --detach --wait --build >"$WORK/compose-up.txt" 2>&1 || { tail -40 "$WORK/compose-up.txt" >&2; exit 1; }

# One known password for every seeded account; seed-dev needs upper and lower case, a digit, a symbol.
E2E_PASSWORD="E2e-$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 16 || true)1a!"
compose exec -T api python -m app.manage seed-dev --password "$E2E_PASSWORD" >"$WORK/seed.json"

cd "$DASHBOARD_DIR"
E2E_API_URL="http://localhost:$API_PORT" E2E_PASSWORD="$E2E_PASSWORD" DASHBOARD_E2E_PORT=$DASHBOARD_PORT \
    npx playwright test -c playwright.api.config.mts "$@"
