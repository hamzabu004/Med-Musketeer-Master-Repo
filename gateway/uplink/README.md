# Gateway uplink (`mm-uplink`)

The fixed gateway's own connection to the cloud (Iteration 4). This first version does three things:
- connects to the cloud's EMQX gateway listener with mutual TLS. It uses the gateway certificate deployed by `mmca deploy`, and verifies the cloud as `cloud.medmusketeer.local` with strict X.509 checks, whatever address it dials;
- reports the gateway's own status (`status-v1` on `mm/gateway/{id}/status`), with the revocation list version it enforces;
- keeps the wearable revocation list and enforces it on the gateway's Mosquitto (`docs/decisions/cloud-backend.md` D16; plan in `docs/iterations/iteration-4-revocation-sync.md`).

Forwarding wearable messages and the outage backlog will be added to this same service. Before forwarding a wearable's message they must check `RevocationStore.listed(device_id)`.

## How the list is enforced

```
cloud ── retained revocation-list-v1 on mm/revocations/wearables ──► mm-uplink
mm-uplink: validate, keep only a newer version, store /var/lib/medmusketeer/revocations.json
        ──► regenerate /var/lib/medmusketeer/wearables.acl (patterns + "user <id> / topic deny #")
        ──► SIGHUP to Mosquitto ──► the wearable can neither publish nor receive
```

- At start, the stored list is applied before the cloud is contacted, so it stays enforced while the cloud is unreachable.
- On every connect, the retained list arrives at once. A newer one is stored, applied, then reported in the gateway's status (`revocation_version`). Older, equal and invalid lists are ignored.
- Device ids must be canonical UUIDs: they are written into the ACL file.
- **Limits:**
  - Mosquitto cannot drop a client identified by its certificate, so a listed wearable stays connected, but nothing it sends goes anywhere.
  - The broker sees the CN only, so the list's `certificates` entries are enforced by the cloud.
- **Runs as `mosquitto`.** Mosquitto 2.x wants its ACL file owned by it with mode 0600 (it warns that later versions refuse anything else). As the same user, the uplink may also signal the broker. The uplink needs the same gateway key the broker uses anyway.

## Install on the gateway Pi

After `setup_mosquitto.sh` and `mmca deploy`, run:

```bash
sudo tools/Fixed-Gateway-Setup/setup_uplink.sh <cloud Pi Tailscale address>
journalctl -u medmusketeer-uplink -f
```

It installs the package into `/opt/medmusketeer/uplink`, writes `/etc/medmusketeer/uplink.toml` (every key is documented in `deploy/uplink.toml.example`), and enables `medmusketeer-uplink.service`. The cloud's certificate chain must verify strictly. A CA made by `mmca` before 2026-10-24 does not; replace it first (`iteration-4-revocation-sync.md`, Slice 0).

## Tests

```bash
cd gateway/uplink
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -m "not interop"   # unit tests
./run_uplink_tests.sh                          # all, with TC-B05 to TC-B08; evidence in docs/testing/evidence/<date>/uplink/
```

TC-B05 to TC-B08 need podman and `eclipse-mosquitto:2.0.21`, the Pi's version. They run the uplink against a gateway broker configured as `setup_mosquitto.sh` does, and a Mosquitto stand-in for the cloud with the cloud certificate. The real EMQX side is covered by TC-C29 and TC-C30.
