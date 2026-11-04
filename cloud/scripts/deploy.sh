#!/usr/bin/env bash
set -Eeuo pipefail

# Deploys a commit of main to the public server: checks it out in this repository and rebuilds the
# stack (compose.yaml + compose.public.yaml). Called by the Deploy workflow over SSH with a key that
# may run nothing else (README, "Continuous deployment"); the commit comes as the SSH command.
#
# Usage: scripts/deploy.sh <sha>              deploy a commit of main, unless a newer one is deployed
#        scripts/deploy.sh --rollback <sha>   deploy a commit of main even if it is older
#
# The whole script is read before it runs (main is called on the last line), because the checkout
# replaces this file.

main() {
    local args=("$@")
    if [[ -n "${SSH_ORIGINAL_COMMAND:-}" ]]; then
        read -r -a args <<< "$SSH_ORIGINAL_COMMAND"
    fi
    local rollback=0
    if [[ "${args[0]:-}" == "--rollback" ]]; then
        rollback=1
        args=("${args[@]:1}")
    fi
    if [[ ${#args[@]} -ne 1 || ! "${args[0]}" =~ ^[0-9a-f]{40}$ ]]; then
        echo "deploy: expected one full commit SHA (40 hex characters)" >&2
        exit 2
    fi
    local sha="${args[0]}"

    local repo
    repo="$(cd "$(dirname "$0")/../.." && pwd)"
    cd "$repo"

    exec 9> "${TMPDIR:-/tmp}/medmusketeer-deploy.lock"
    flock 9

    git fetch --quiet origin main
    if ! git merge-base --is-ancestor "$sha" origin/main; then
        echo "deploy: $sha is not a commit of main" >&2
        exit 1
    fi
    local current
    current="$(git rev-parse HEAD)"
    if [[ $rollback -eq 0 && "$sha" != "$current" ]] && git merge-base --is-ancestor "$sha" "$current"; then
        echo "deploy: $current, newer than $sha, is already deployed; nothing to do"
        exit 0
    fi

    git checkout --quiet --detach "$sha"
    echo "deploy: checked out $(git log --oneline -1)"

    cd cloud
    docker compose -f compose.yaml -f compose.public.yaml up -d --wait --build --remove-orphans
    docker image prune -f > /dev/null
    docker compose -f compose.yaml -f compose.public.yaml ps --format '{{.Service}}: {{.Status}}'
    echo "deploy: $sha is live"
    exit 0
}

main "$@"
