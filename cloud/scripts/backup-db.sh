#!/usr/bin/env bash
set -Eeuo pipefail

# Dumps every database of the stack (medmusketeer and zitadel, with roles) to a gzip file, readable
# only by its owner. Restoring also needs the same .env: ZITADEL's data is sealed with its masterkey.
# Usage: scripts/backup-db.sh [directory]   (default: cloud/backups)

readonly CLOUD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
dir="${1:-$CLOUD_DIR/backups}"
read -r -a compose <<< "${MM_COMPOSE:-docker compose}"

umask 077
mkdir -p "$dir"
target="$dir/medmusketeer-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
cd "$CLOUD_DIR"
"${compose[@]}" exec -T postgres pg_dumpall -U postgres | gzip > "$target"
[[ ${PIPESTATUS[0]} -eq 0 ]] || { rm -f "$target"; echo "backup-db: pg_dumpall failed" >&2; exit 1; }
echo "$target"
