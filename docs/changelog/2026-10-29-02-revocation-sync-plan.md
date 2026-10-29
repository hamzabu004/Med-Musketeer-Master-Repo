# Wearable revocation on the gateway: push + cache decided and planned (Iteration 4)

- **Date:** 2026-10-29
- **Type:** decision
- **Module:** M5 gateway, M7 cloud
- **Commits:** see `git log -- docs/iterations/iteration-4-revocation-sync.md`

## What changed
- **Decided:** the cloud pushes the full list of revoked and suspended wearables to every gateway as a retained, versioned message on `mm/revocations/wearables`. Each gateway caches it, enforces it while the cloud is unreachable, and picks up the current list as soon as it reconnects. Revoking a gateway also disconnects it from EMQX at once.
- **Assumption recorded:** the gateway normally has internet access; losing the cloud is temporary.
- The earlier candidate in `stack.md` (a CA-signed list the gateway pulls) is replaced. The list needs no signature: it only arrives over the gateway's mTLS session.
- **Plan:** `docs/iterations/iteration-4-revocation-sync.md`, with four slices:
  - Slice 0: a spike on the Mosquitto enforcement mechanism;
  - Slice 1: the cloud's list, publishing and gateway disconnect;
  - Slice 2: the gateway's cache and enforcement;
  - Slice 3: outage handling (clock, quarantine of backlog sent after a revocation).

  The plan reserves test IDs TC-C28 to TC-C32 and TC-B05 to TC-B08.
- **Docs:** `stack.md` (revocation section, open steps), `cloud-backend.md` (new D16), `mqtt-fixed-path-topics.md` (gateway subscription), `gaps.md`.

## Why
A wearable revoked before its certificate expires is still accepted by the gateway's Mosquitto, which checks only the chain and CN, and the gateway's local classification and alerts run on its data. A live check per connect would stop monitoring during every outage, and a CRL would need `ca.key` online.

## Evidence
None (no code yet).
