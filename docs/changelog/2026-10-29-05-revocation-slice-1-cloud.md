# Revocation sync, Slice 1: the cloud publishes the wearable revocation list and disconnects revoked gateways (Iteration 4)

- **Date:** 2026-10-29
- **Type:** code
- **Module:** M7 cloud
- **Commits:** see `git log -- cloud/ shared/contracts/revocation-list-v1.schema.json`

## What changed
- **Migration 0004:**
  - `revocation_state`: one row holding `version`, `published_version` and `published_at`. The API may update it but not insert or delete.
  - `devices.status_changed_at`, set on every status change.
  - `devices.revocation_version`, the list version a gateway reported.
- **The list** (`app/revocation.py`, contract `revocation-list-v1` in `shared/contracts/`):
  - Content: suspended and revoked wearables, plus revoked, unexpired certificates of wearables that are not listed.
  - Version: a registry change that alters the list raises the version in its own transaction.
  - Publishing: the list is published after the commit, retained on `mm/revocations/wearables`, through EMQX's REST API (`app/emqx_api.py`, key `mm-api`).
  - Reconciler: publishes any unpublished version every 5 seconds, and the whole list every 5 minutes.
  - Consistency: each list is built in one REPEATABLE READ snapshot, so its version matches its contents.
- **Gateways:**
  - Suspending or revoking a gateway, or revoking one of its credentials, disconnects it at once (reason 0x98).
  - Gateways may subscribe to the list's topic (D5); no MQTT client may publish to it.
- **Staleness:**
  - `status-v1` gains an optional `revocation_version` for a gateway's own status. Ingestion stores it, and rejects it on a wearable's status.
  - New endpoint `GET /admin/revocation` (system admin) returns the version, the published version, and the active gateways behind it.
- **EMQX:**
  - The API key is bootstrapped from the new secret `EMQX_API_SECRET`, which `mm-entrypoint.sh` writes into the bootstrap file.
  - Retained messages are stored on disc.
- **Configuration:** new settings `MM_EMQX_API_URL`, `MM_EMQX_API_SECRET`, `MM_REVOCATION_POLL_S` and `MM_REVOCATION_REPUBLISH_S`. Compose passes `REVOCATION_REPUBLISH_S`, default 300.
- **Tests:**
  - TC-C28 and TC-C31 at the API against the database, with EMQX faked.
  - TC-C29 and TC-C30 through the real stack.
  - Existing tests updated: the D5 rules, the contracts, the D9 matrix row, the schema's table list and privileges.
  - The test MQTT client now records broker disconnects.
  - The test stack sets the full-republish interval to a day, so TC-C29 can tell disc storage from a republish.
- **Docs:** `cloud-backend.md` (D5, D16), `stack.md`, `gaps.md` (immediate gateway disconnect built), `iteration-4-revocation-sync.md`, `test_traceability.md`, `cloud/README.md`.
- **Found while testing:** paho-mqtt 2.1.0 reads a DISCONNECT's reason code only when the packet is longer than 2 bytes, so it reports EMQX's kick (2 bytes: 0x98 and empty properties) as "Normal disconnection"; `mosquitto_sub` reads the same kick as 152. TC-C30 therefore checks that the DISCONNECT came from the server and that the reconnect is refused, and D16 warns the gateway's uplink not to rely on paho's reason code.

## Upgrading a dev stack
Add `EMQX_API_SECRET` to `cloud/.env` (the command is in `cloud/README.md`), then run `docker compose up -d --build`.

## Why
This is the cloud half of the push + cache decision (D16). Gateways need a list to cache before Slice 2 can enforce one. Disconnecting revoked gateways closes the D4 gap where a revoked gateway kept its session until it reconnected.

## Evidence
`docs/testing/evidence/2026-10-29/cloud-revocation/`: 393 tests pass (`pytest.txt`, `junit.xml`, `coverage.xml`, `environment.txt`), with the stack's compose output and per-case results in `stack/` (the API and EMQX logs stay local: `*.log` is ignored). Highlights from `stack/tc_c29_c30_revocation.json`:
- a new list version reached a subscribed gateway 0.068 s after the revocation;
- the forged publish was refused;
- the retained list survived EMQX being recreated with no republish in between;
- gateways were disconnected 17 to 33 ms after a credential revoke, a suspend or a revoke, and their reconnect was refused.

Coverage of `app/emqx_api.py` (37%) counts only in-process calls; the stack tests exercise it inside the API container.
