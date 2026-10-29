# Revocation sync, Slice 0: enforcement mechanisms chosen, CA replacement decided (Iteration 4)

- **Date:** 2026-10-29
- **Type:** decision
- **Module:** M5 gateway, M7 cloud, M1 CA tool
- **Commits:** see `git log -- docs/iterations/iteration-4-revocation-sync.md`

## What changed
- **Gateway broker:** the uplink regenerates the wearable ACL file with a `topic deny #` block per listed wearable and reloads Mosquitto with SIGHUP. Measured on 2.0.21 (the Pi) and 2.1.2:
  - a listed wearable's publishes are refused and nothing is delivered to it, on an open connection too;
  - its connection stays open;
  - other wearables are unaffected.
- **Rejected:** the dynamic security plugin. It does not authenticate certificate identities, and `disableClient` neither drops nor refuses the client.
- **Accepted limits:**
  - the gateway cannot disconnect a revoked wearable;
  - revoking one credential of an active wearable is enforced by the cloud only; on the gateway it means suspending the wearable.
- **EMQX** (6.3.2, verified):
  - the API key comes from `api_key.bootstrap_file`;
  - the REST retained publish passes the deny-all authorisation, and clients cannot overwrite the topic;
  - gateways are found by username and disconnected with reason 0x98;
  - the retainer must use `storage_type = disc`, because the default `ram` loses the list when the container is recreated.
- **CA:** the current CA has no Subject Key Identifier, so the uplink's strict verification (Python 3.13+) would refuse its chains. It will be replaced, and the gateway, the wearable and the cloud certificate re-issued with their device ids kept. The steps are in the plan. Not carried out yet.
- **Docs:** `iteration-4-revocation-sync.md` (Slice 0 results, design, file list, risks, exit criterion 1), `stack.md`, `cloud-backend.md` D16, `gaps.md`.

## Why
Slice 0 had to settle the one unknown in the plan, how the gateway's Mosquitto can enforce the list, and confirm the EMQX features Slice 1 relies on. The CA decision unblocks the uplink.

## Evidence
`docs/testing/evidence/2026-10-29/revocation-spike/`: two scripts, `results.json`, `emqx-results.json`, broker and EMQX logs.
