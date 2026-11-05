# The fixed gateway connects to the cloud VM; TC-C27 and backups deferred

- **Date:** 2026-11-05
- **Type:** ops
- **Module:** M5 gateway | M7 cloud
- **Commits:** 810e7e8 (gateway connection, deferrals, evidence), e9bda70 (status updates)

## What changed
- The production registry at `medmusketeer.site` has its first devices. Through the dashboard, the system admin registered the fixed gateway `64e33c48-5c41-4afe-8772-e937e51d67a0` and the wearable `8f0f5194-93bf-4e1d-8e72-f96fa1f3df21`, both as production devices (not testbed). Each got its certificate's SHA-256 fingerprint as an `x509_mtls` credential and was activated. Both certificates were issued by the CA that replaced the original on 2026-10-30.
- The gateway's uplink (`/etc/medmusketeer/uplink.toml` on the Pi) now dials `mqtt.medmusketeer.site:8883` instead of the cloud Pi's Tailscale address. The old file is kept as `uplink.toml.bak-20261105`.
- `setup_uplink.sh`, `deploy/uplink.toml.example` and the uplink README now use the cloud's public MQTT name as the example address. The README also says how to move an installed gateway to a new address.
- Iteration 3's last two items are deferred and tracked in `gaps.md` ("Non-functional / ops"):
  - TC-C27, the smoke suite against the server;
  - scheduled backups copied off the VM.
- Statuses brought up to date in Iterations 2 and 4, `gaps.md`, `stack.md`, `test_traceability.md` and `hardware_test_procedures.md`:
  - The CA replacement decided on 2026-10-29 was carried out on 2026-10-30. A first run that day made future-dated certificates (wrong clock) and was redone; its archive is under `ca/archive/` on the custodian's machine. The final CA is `90F91212…`. The gateway, wearable and cloud certificates were re-issued from it, then deployed, flashed and installed.
  - The Pi is reachable again. H-W01 to H-W03, H-B and H-B06 are unblocked but not run yet.

## Why
Slice 6 put the cloud on the Oracle VM (D18), but no gateway had connected to it yet. The two deferred items each need a decision first: where the backups go and how they are encrypted, and what test data the smoke suite may create on production.

## Evidence
`docs/testing/evidence/2026-11-05/gateway-cloud/`:
- `gateway_uplink.txt`, from the Pi:
  - the uplink's address and pinned name, and the gateway certificate's fingerprint;
  - from 04:13 UTC, before activation, the cloud refused it with "Not authorized";
  - at 04:20:35 it connected, stored revocation list version 1 (empty) and reloaded the gateway broker's ACL.
- `cloud_registry.txt`, from the VM:
  - both devices and credentials active;
  - the gateway's `online` connectivity event at 04:20:35 and its `last_seen`;
  - the audit rows of the registration;
  - EMQX's `not_authorized` decisions for the gateway before activation.

The TLS handshake succeeded in both directions (the uplink's strict X.509 checks with the `cloud.medmusketeer.local` pin; EMQX's client-certificate check). The refusals came from the registry check, not from TLS.

Not covered: wearable data through the gateway to the cloud. The uplink does not forward wearable messages yet; that is Iteration 4's uplink bridge.
