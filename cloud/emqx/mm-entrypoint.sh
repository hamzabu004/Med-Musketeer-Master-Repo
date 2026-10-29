#!/usr/bin/env bash
set -Eeuo pipefail

# Renders etc/emqx.conf from the template, then starts EMQX through the image's own entrypoint.
# EMQX 6 does not substitute environment variables in emqx.conf, so the secrets are filled in here.
# The gateway listener is enabled only when the cloud certificate is installed
# (cloud/scripts/install-emqx-certs.sh); without it EMQX still starts, with a warning.

readonly ETC=/opt/emqx/etc
readonly CERTS="$ETC/certs/mm"

for name in MM_EMQX_HOOK_SECRET MM_EMQX_NODE_COOKIE MM_EMQX_API_SECRET; do
    # Alphanumeric only, so the value cannot break out of the HOCON string or the sed expression.
    if [[ ! "${!name:-}" =~ ^[A-Za-z0-9]{24,}$ ]]; then
        echo "mm-entrypoint: $name must be set to at least 24 letters and digits" >&2
        exit 1
    fi
done

enable=true
for file in ca.crt server.crt server.key; do
    if [[ ! -r "$CERTS/$file" ]]; then
        echo "mm-entrypoint: WARNING $CERTS/$file is missing; the gateway listener (8883) is disabled." >&2
        echo "mm-entrypoint: install the cloud certificate with cloud/scripts/install-emqx-certs.sh" >&2
        enable=false
        break
    fi
done

umask 077
sed -e "s/@MM_EMQX_HOOK_SECRET@/$MM_EMQX_HOOK_SECRET/g" \
    -e "s/@MM_EMQX_NODE_COOKIE@/$MM_EMQX_NODE_COOKIE/g" \
    -e "s/@MM_GATEWAY_LISTENER_ENABLE@/$enable/g" \
    "$ETC/emqx.conf.template" > "$ETC/emqx.conf"
if grep -q '@MM_' "$ETC/emqx.conf"; then
    echo "mm-entrypoint: unrendered placeholder in emqx.conf" >&2
    exit 1
fi
# key:secret:role. administrator: the API publishes and disconnects clients (D16).
printf 'mm-api:%s:administrator\n' "$MM_EMQX_API_SECRET" > "$ETC/mm_api_keys.txt"

# Every client is authenticated by the API's hooks. If EMQX starts while `api` does not resolve,
# its HTTP authenticators stay down until their next health check (about 15 s) and refuse every
# client meanwhile. compose orders the start, but not Docker's restarts (unless-stopped, after a
# reboot), so wait here too; after MM_API_WAIT_S EMQX starts anyway and recovers on its own.
readonly API_LIVEZ="${MM_API_LIVEZ_URL:-http://api:8000/livez}"
for ((waited = 0; waited < ${MM_API_WAIT_S:-120}; waited += 2)); do
    curl -fsS -o /dev/null --max-time 2 "$API_LIVEZ" && break
    ((waited % 20 == 0)) && echo "mm-entrypoint: waiting for $API_LIVEZ" >&2
    sleep 2
done

exec /usr/bin/docker-entrypoint.sh "$@"
