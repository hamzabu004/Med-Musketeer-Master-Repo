# Iteration 4 — Revocation push and cache (plan)

- **Owner:** Hamza Tariq (M7 cloud platform, M1 CA tool)
- **Status:** Planned (2026-10-29). Not started; waits for the Iteration 3 ingestion work to land.
- **Part of:** Iteration 4 (gateway uplink). The cache lives in the gateway's uplink service, so it is built alongside it.
- **Depends on:** `stack.md` "Gateway/wearable credential revocation (fixed path)" (this plan replaces its pending candidate), `cloud-backend.md` D4 and D5, `mqtt-fixed-path-topics.md`, `tools/Fixed-Gateway-Setup/setup_mosquitto.sh`
- **Assumption:** the gateway normally has internet access; losing the cloud is temporary, never permanent.

## Goal

A wearable whose device or credential is revoked is refused by every gateway: within seconds when the gateway is online, and as soon as it reconnects after an outage. While the cloud is unreachable, the gateway keeps enforcing the last list it received and keeps monitoring.

## Why push + cache

| Option | Online | During an outage | Verdict |
|---|---|---|---|
| Live check per wearable connect | Current | Must refuse every wearable (stops monitoring) or accept every wearable (ignores revocation) | Rejected |
| CRL via Mosquitto `crlfile` | Current after re-signing | Enforced | Rejected: a CRL must be signed with `ca.key`, which never leaves the custodian's machine |
| **Pushed list, cached on the gateway** | Within seconds | Last received list enforced | **Chosen** |

## Design

**Topic:** `mm/revocations/wearables`, retained, QoS 1. Published by the cloud, subscribe-only for gateways. It is a single topic, not one per gateway, because every gateway needs the same list and the list is not secret.

**Payload `revocation-list-v1`** (schema in `shared/contracts/`):

```json
{
  "version": 42,
  "issued_at": "2026-11-03T10:15:00Z",
  "devices":      [{"device_id": "<uuid>", "status": "revoked|suspended"}],
  "certificates": [{"device_id": "<uuid>", "fingerprint": "<64 hex>", "not_after": "..."}]
}
```

- `version` is a counter in the database that increases with every change. The gateway ignores a list whose version is not newer than the one it has stored. That keeps a delayed duplicate from undoing a newer list.
- `devices` holds wearables that are suspended or revoked. `certificates` holds single revoked credentials of a wearable that is still active, for example the old certificate after a rotation.
- A certificate is left off the list once `not_after` has passed, because expiry already refuses it. The list stays small.
- The full list is sent every time, never a diff, so a gateway that missed messages is correct after reading one.
- **No signature:** the list arrives only over the gateway's mTLS session with EMQX, and the topic is publish-denied to everyone except the cloud. An attacker who can rewrite the stored file on the gateway already holds the gateway's key.

**Cloud side:**
1. Every registry change that affects a wearable (suspend, reactivate, revoke a device, revoke a credential) increases `version` and republishes the list. The publish happens in the same transaction as the change, or through an outbox table, so a crash cannot leave the database and the retained message out of step.
2. The API publishes through EMQX's REST API (`POST /api/v5/publish`, `retain: true`) with an EMQX API key from `.env`.
3. The same EMQX client disconnects a gateway at once when its device or credential is revoked (D4 "may", `gaps.md:18`).
4. **Bounded staleness:** each gateway reports the list version it is enforcing in its `mm/gateway/{cn}/status` message. The registry stores it, and the dashboard flags a gateway that is behind the current version.

**Gateway side (uplink service):**
1. Subscribes to `mm/revocations/wearables` on connect. The retained message arrives immediately, so reconnecting needs no extra sync step.
2. Validates the payload against the schema, checks the version, and writes it atomically (temp file + rename) to `/var/lib/medmusketeer/revocations.json`.
3. Applies it to the local Mosquitto: refuses revoked wearables on connect and disconnects any that are already connected. The mechanism is chosen in Slice 0.
4. On start, loads the stored file before accepting wearables. If there is no file yet (first boot), it stays in the provisioning state until it has received a list once.

**Outage window:** a wearable revoked *during* an outage can still connect to an offline gateway. The gateway accepts this rather than stopping monitoring. When the backlog is uploaded, the cloud compares each message's timestamp with the wearable's revocation time and marks later data `quarantined` instead of ingesting it as a normal record.

## Slices

### Slice 0 — Decisions and spike (S)
- **Mosquitto enforcement mechanism (spike, the main unknown).** Candidates:
  - The dynamic security plugin (`disableClient` refuses the client and disconnects it; check that it works with `use_identity_as_username`).
  - An auth plugin that reads the stored file (e.g. mosquitto-go-auth with a files backend).
  - Moving the wearable listener to a broker with a hook API.

  Pick the one that does both "refuse on connect" and "disconnect now" on Pi OS's Mosquitto version.
- **Certificate-level entries:** how the chosen mechanism sees a wearable's fingerprint. If it only sees the username (CN), revoking a single credential has to suspend the device until it is re-issued; record that limit.
- Confirm the decision on the CA's missing key identifiers (`gaps.md:17`) first. The uplink's TLS client depends on it.
- Record the decisions in `stack.md` (replacing the pending revocation section), `cloud-backend.md` (D5 subscribe rule, new D-number for the list), and `gaps.md`.

### Slice 1 — Cloud: list, publish, disconnect (M)
- Migration: `revocation_list_version` counter and a publish outbox.
- Build the list from `devices` and `device_credentials`; republish on every affecting change; republish everything on API start (repairs a lost retained message).
- EMQX REST client: publish retained, disconnect a client. Revoking a gateway now disconnects it immediately.
- D5: gateways may subscribe to `mm/revocations/wearables`; everyone else is denied publishing to it (`broker.py`).
- Tests (TC-C): the list follows each registry transition; the version increases; a gateway receives the retained list on connect; another gateway cannot publish to the topic; a revoked gateway is disconnected within seconds.

### Slice 2 — Gateway: cache and enforce (M)
- The uplink service subscribes, validates, rejects older versions, stores atomically, and applies the list to Mosquitto.
- `setup_mosquitto.sh` gains the chosen plugin or settings.
- Reports the version it is enforcing in its status message.
- Tests (TC-G, a proposed new prefix for gateway tests): a revoked wearable is refused and an already-connected one is dropped; an older or invalid list is ignored; the list survives a restart; with the cloud cut off, the stored list is still enforced and non-revoked wearables keep working.

### Slice 3 — Outage handling (S–M)
- Gateway clock: fit the RTC battery, or install `fake-hwclock`, so the time never jumps back after a reboot. Each backlog record carries whether the clock was synchronised.
- Cloud: quarantine backlog data from a wearable after its revocation time. Gated on the backlog payload being defined (`gaps.md:37`).
- Dashboard: show a gateway's list as stale when its reported version is behind.
- Tests: revoke during a simulated outage, reconnect, and check that the gateway gets the list immediately, disconnects the wearable, and that data sent after the revocation is quarantined.

## Exit criteria

1. Revoking or suspending a wearable makes every online gateway refuse it and disconnect it within 10 seconds.
2. A gateway cut off from the cloud keeps enforcing its last list and keeps serving non-revoked wearables; on reconnect it enforces the current list without manual action.
3. Revoking a gateway disconnects it from EMQX at once.
4. The dashboard shows each gateway's enforced list version and flags stale ones.
5. Every test has a TC ID in `test_traceability.md` and stored evidence.

## Out of scope

- Short-lived gateway certificates with automatic renewal: they need an online signing service and the Device Intermediate CA (`stack.md:362`). Planned for FYP-2.
- Revoking a gateway in the eyes of wearables: wearables accept any registered gateway (`stack.md:190`). A revoked gateway that stays offline can keep serving wearables locally until it reconnects. This is a documented residual risk.
- Compromise of `ca.key`: the only remedy is replacing the CA and re-issuing every device.

## Risks

| Risk | Mitigation |
|---|---|
| No Mosquitto mechanism does both refuse and disconnect cleanly | Slice 0 spike first; fallback: put the wearable listener behind a broker with a hook API |
| The database and the retained message drift apart | Outbox plus a full republish on API start |
| The gateway clock is wrong after an offline reboot | RTC or `fake-hwclock`; backlog records say whether the clock was synchronised |
