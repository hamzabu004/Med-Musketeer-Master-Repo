#!/usr/bin/env bash
set -Eeuo pipefail

# Renders etc/emqx.conf from the template, then starts EMQX through the image's own entrypoint.
# EMQX 6 does not substitute environment variables in emqx.conf, so the secrets are filled in here.
# The gateway listener is enabled only when the cloud certificate is installed
# (cloud/scripts/install-emqx-certs.sh); without it EMQX still starts, with a warning.

readonly ETC=/opt/emqx/etc
readonly CERTS="$ETC/certs/mm"

for name in MM_EMQX_HOOK_SECRET MM_EMQX_NODE_COOKIE; do
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

exec /usr/bin/docker-entrypoint.sh "$@"
