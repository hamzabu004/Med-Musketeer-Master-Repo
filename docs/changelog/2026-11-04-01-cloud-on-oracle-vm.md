# Cloud deployed to an Oracle Cloud VM at medmusketeer.site

- **Date:** 2026-11-04
- **Type:** ops
- **Module:** M7 cloud | M8 dashboard
- **Commits:** pending

## What changed
- The cloud stack and the dashboard run on an Oracle Cloud VM (`VM.Standard.E5.Flex`, 4 OCPU, 12 GB, Oracle Linux 9, Singapore) instead of the second Raspberry Pi. They are public at `app`, `api` and `auth.medmusketeer.site` over HTTPS, and gateways connect to `mqtt.medmusketeer.site:8883` with mutual TLS. Recorded as `cloud-backend.md` D18. The hosting row in `stack.md`, Iteration 3's Slice 6, Iteration 6's deployment section and `gaps.md` are updated to match.
- Docker's data is on a separate 100 GB block volume. `cloud/README.md` has the server set-up steps.
- Postgres stays in the stack. Oracle's managed PostgreSQL was considered and rejected because it does not offer TimescaleDB.
- The first VM was replaced on 2026-11-03 after the passphrase of its only SSH key was forgotten. Nothing on it was kept except the block volume, whose old stack data was deleted.

## Why
The dashboard has to be reachable by users outside the tailnet, and browsers allow its sign-in only over HTTPS. The VM also removes the risk that the Pi's memory would not hold the stack.

## Evidence
On 2026-11-04 the following checks passed:
- Valid Let's Encrypt certificates for the three web addresses.
- From outside, only 22, 80, 443 and 8883 answer; HTTP redirects to HTTPS; `/internal` and `/docs` answer 404.
- A headless browser signed in as the system admin through ZITADEL and reached `/system/dashboard` (`/me` 200).
- All eight services were healthy after a reboot, using about 1.9 GB of memory.

Not yet done: TC-C27 against the server, scheduled off-VM backups, and the gateway's connection.
