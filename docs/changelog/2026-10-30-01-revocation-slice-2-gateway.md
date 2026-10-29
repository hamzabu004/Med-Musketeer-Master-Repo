# Revocation sync, Slice 2: the gateway uplink keeps and enforces the wearable revocation list (Iteration 4)

- **Date:** 2026-10-30
- **Type:** code
- **Module:** M5 gateway
- **Commits:** see `git log -- gateway/uplink tools/Fixed-Gateway-Setup`

## What changed
- **New: a minimal gateway uplink** (`gateway/uplink`, `mm-uplink`). It connects to the cloud's EMQX gateway listener with mutual TLS, using the gateway certificate, and verifies the cloud by its pinned name with strict X.509 checks. It reports the gateway's status with the `revocation_version` it enforces. Forwarding wearable messages and the backlog will be added to it later; the scope was decided on 2026-10-30.
- **The list on the gateway:**
  - Each list is validated against the shared `revocation-list-v1` schema, which ships with the package. A test keeps that copy identical to `shared/contracts/`.
  - Device ids must be canonical UUIDs, because they are written into the ACL file.
  - Only a newer version is kept, stored atomically in `/var/lib/medmusketeer/revocations.json`, and loaded and applied at start before the cloud is contacted.
- **Enforcement:**
  - The uplink regenerates `/var/lib/medmusketeer/wearables.acl` (the patterns plus a `topic deny #` block per listed wearable) and reloads Mosquitto by SIGHUP. This is the Slice 0 mechanism.
  - The broker is reloaded only when the file changes, a failed reload is retried, and the version reported is the one loaded.
- **Runs as `mosquitto`.** Mosquitto 2.x warns that later versions will refuse an ACL file not owned by it or readable by others. Running as `mosquitto`, the uplink owns the file (mode 0600) and can signal the broker without a sudo rule.
- **Setup:**
  - `setup_mosquitto.sh` now writes the first wearable ACL to `/var/lib/medmusketeer/wearables.acl` and leaves an existing one alone.
  - New `setup_uplink.sh` installs the uplink (venv, `/etc/medmusketeer/uplink.toml`, `medmusketeer-uplink.service`).
- **Tests:** unit tests, plus TC-B05 to TC-B08 against Mosquitto 2.0.21 containers (a gateway broker set up as on the Pi, and a cloud stand-in with the cloud certificate). There is a new runner, `run_uplink_tests.sh`, and a new CI workflow, `gateway.yml`.
- **Docs:** `iteration-4-revocation-sync.md` (Slice 2 as built), `stack.md`, `cloud-backend.md` D16, `mqtt-fixed-path-topics.md` (the generated ACL file), `gaps.md`, `test_traceability.md`, `hardware_test_procedures.md` (new H-B06), and `gateway/uplink/README.md`.

## Why
This is the gateway half of push + cache (D16). A revoked wearable is now refused by the gateway itself, and keeps being refused while the cloud is unreachable.

## Evidence
`docs/testing/evidence/2026-10-30/uplink/` has 20 passing tests (`pytest.txt`, `junit.xml`, `environment.txt`), and in `broker/` the broker logs, client output and `tc_b05_b08_uplink.json`:
- A list was enforced and reported 0.16 s after the cloud published it. On the listed wearable's open connection, publishes were refused and commands stopped arriving; another wearable was unaffected.
- Older, equal and invalid lists were ignored, and so was a list with an injected ACL line.
- After a restart with the cloud down, the stored list was applied before any connection was made.
- During the outage the list held. 3.9 s after the cloud came back, the newer list was enforced: one wearable lifted, another listed.

**Not yet run on the Pi** (H-B06): the uplink's strict verification needs the CA replacement from Slice 0 first.
