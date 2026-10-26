#!/usr/bin/env bash
set -Eeuo pipefail

# Installs the cloud server certificate (issued with `mmca issue cloud`) into the emqx-certs volume
# and restarts EMQX if it is running, so the gateway listener (8883) starts with it.
#
# Usage: scripts/install-emqx-certs.sh [mmca-root] [-- extra compose options]
#   mmca-root  the CA tool's data directory (default ~/medmusketeer-ca); reads ca/ca.crt,
#              cloud/server.crt and cloud/server.key
#   e.g.       scripts/install-emqx-certs.sh /tmp/ca -- -p mm-cloud-tc --env-file test.env
#
# The files are streamed into the volume (no bind mount, see README), owned by EMQX's user and
# with the key at mode 600. Nothing is installed unless the certificate chains to the CA, is a
# server certificate for cloud.medmusketeer.local, and matches the key.

readonly CLOUD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
readonly NAME="cloud.medmusketeer.local"

root="$HOME/medmusketeer-ca"
if [[ $# -gt 0 && "$1" != "--" ]]; then
    root="$1"
    shift
fi
[[ "${1:-}" == "--" ]] && shift
read -r -a compose <<< "${MM_COMPOSE:-docker compose}"
compose+=("$@")

ca="$root/ca/ca.crt"
cert="$root/cloud/server.crt"
key="$root/cloud/server.key"
for file in "$ca" "$cert" "$key"; do
    [[ -r "$file" ]] || { echo "install-emqx-certs: cannot read $file" >&2; exit 1; }
done

openssl verify -CAfile "$ca" -purpose sslserver -verify_hostname "$NAME" "$cert" >/dev/null \
    || { echo "install-emqx-certs: $cert is not a server certificate for $NAME from this CA" >&2; exit 1; }
# EMQX does not need it, but strict clients (Python 3.13+'s default TLS context, as a gateway's
# uplink would use) refuse a chain without key identifiers, which CAs made by mmca before
# 2026-10-24 lack.
if ! openssl verify -CAfile "$ca" -x509_strict "$cert" >/dev/null 2>&1; then
    echo "install-emqx-certs: WARNING the chain fails strict X.509 verification (missing key identifiers);" >&2
    echo "install-emqx-certs: strict TLS clients will refuse it. See docs/decisions/gaps.md." >&2
fi
if [[ "$(openssl x509 -in "$cert" -noout -pubkey)" != "$(openssl pkey -in "$key" -pubout)" ]]; then
    echo "install-emqx-certs: $key does not match $cert" >&2
    exit 1
fi

staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
install -m 644 "$ca" "$staging/ca.crt"
install -m 644 "$cert" "$staging/server.crt"
install -m 600 "$key" "$staging/server.key"

cd "$CLOUD_DIR"
tar -C "$staging" -c ca.crt server.crt server.key \
    | "${compose[@]}" --profile tools run --rm -T emqx-certs-install
echo "Installed the certificate for $NAME ($(openssl x509 -in "$cert" -noout -fingerprint -sha256 | cut -d= -f2))."

if [[ -n "$("${compose[@]}" ps --status running --quiet emqx 2>/dev/null)" ]]; then
    "${compose[@]}" restart emqx
    echo "Restarted EMQX."
fi
