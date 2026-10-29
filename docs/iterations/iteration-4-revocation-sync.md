# Iteration 4 — Revocation push and cache

- **Owner:** Hamza Tariq (M7 cloud platform, M5 gateway)
- **Status:** Planned (2026-10-29). Design decided (`stack.md` "Gateway/wearable credential revocation", `cloud-backend.md` D16); the Mosquitto enforcement mechanism is chosen in Slice 0.
- **Part of:** Iteration 4 (gateway uplink). The gateway side lives in the uplink service, so Slice 2 starts once the uplink can connect to EMQX.
- **Depends on:** `cloud-backend.md` D4, D5, D15; `mqtt-fixed-path-topics.md`; `tools/Fixed-Gateway-Setup/setup_mosquitto.sh`; the decision on the CA's missing key identifiers (`gaps.md`)
- **Assumption:** the gateway normally has internet access. Losing the cloud is temporary, never permanent.

## Goal

A wearable whose device or credential is revoked is refused by every gateway: within seconds when the gateway is online, and as soon as it reconnects after an outage. While the cloud is unreachable, the gateway keeps enforcing the last list it received and keeps monitoring. A revoked gateway is disconnected from the cloud at once.

## What exists today

| Leg | Today | After this iteration |
|---|---|---|
| Gateway → EMQX, connect | Refused when the certificate is not an active credential of an active gateway (`broker.py`) | Same |
| Gateway → EMQX, live session | Kept until reconnect; topic access lost within EMQX's 1-minute authorisation cache if the *device* is suspended or revoked | Disconnected at once |
| Wearable data → database | Rejected when the wearable is not active (`ingest.py:111`) | Same, plus quarantine of outage backlog sent after the revocation |
| Wearable → gateway Mosquitto | Chain + CN only; a revoked wearable is accepted, and the gateway's local classification and alerts run on its data | Refused by the broker and ignored by the gateway's services |

## Why push + cache

| Option | Online | During an outage | Verdict |
|---|---|---|---|
| Live check per wearable connect | Current | Must refuse every wearable (stops monitoring) or accept every wearable (ignores revocation) | Rejected |
| CRL via Mosquitto `crlfile` | Current after re-signing | Enforced | Rejected: a CRL must be signed with `ca.key`, which never leaves the custodian's machine |
| **Pushed list, cached on the gateway** | Within seconds | Last received list enforced | **Chosen** |

## Design

### The list

**Topic:** `mm/revocations/wearables`, retained, QoS 1. Only the cloud publishes it; gateways may only subscribe. One topic for all gateways: every gateway needs the same list, and it is not secret.

**Payload `revocation-list-v1`** (Pydantic model in `contracts.py`, schema generated into `shared/contracts/`):

```json
{
  "v": 1,
  "version": 42,
  "issued_at": "2026-11-03T10:15:00Z",
  "devices":      [{"device_id": "<uuid>", "status": "suspended|revoked", "since": "<time>"}],
  "certificates": [{"device_id": "<uuid>", "fingerprint": "<64 hex>", "not_after": "<time>"}]
}
```

- `version` comes from a database counter that increases with every change. The gateway ignores a list whose version is not newer than the one it has stored, so a delayed duplicate cannot undo a newer list.
- `devices`: wearables that are suspended or revoked. `certificates`: revoked credentials of a wearable that is still active (e.g. the old certificate after a rotation). A certificate is dropped once `not_after` has passed, because expiry already refuses it.
- Always the full list, never a diff: a gateway that missed messages is correct after reading one.
- **No signature:** it arrives only over the gateway's mTLS session, and no client but the cloud can publish to the topic. Anyone who can rewrite the stored file on the gateway already holds the gateway's key.

### Cloud

1. **Publishing:** the API publishes through EMQX's REST API (`POST /api/v5/publish`, `retain: true`) with an API key bootstrapped from `.env`. A REST publish does not go through client authorisation, so no MQTT account gets publish rights to the topic.
2. **When:** every registry change that affects a wearable (activate, suspend, revoke a device, revoke a credential) increases the counter and writes an outbox row in the same transaction. After commit, the API publishes the current list and marks the row sent. A reconciler task in the API republishes when the outbox has unsent rows, when the API starts, and every 5 minutes. The repeat costs nothing (gateways ignore an equal version) and repairs a retained message lost in an EMQX restart.
3. **Gateway disconnect:** revoking or suspending a gateway, or revoking one of its credentials, kicks its sessions through the REST API (`GET /api/v5/clients?username=…`, then `DELETE /api/v5/clients/{clientid}`). Closes the D4 "may" in `gaps.md`.
4. **Staleness:** the gateway adds `revocation_version` to its own `status-v1` message. Ingestion stores it on the gateway, and the system admin's device screens flag a gateway that is behind the current version.

### Gateway (three layers)

1. **Cache (uplink service):** subscribes to the topic on every connect (the retained message arrives at once, so reconnecting needs no sync step), validates the payload, ignores older versions, and writes `/var/lib/medmusketeer/revocations.json` atomically (temp file + rename). On start it loads the stored file before anything else.
2. **Broker:** the uplink applies the list to the local Mosquitto, so a revoked wearable can neither publish nor subscribe, and is disconnected where the mechanism allows. The mechanism is chosen in Slice 0 (below).
3. **Services:** the uplink does not forward, and the local classifier does not process, messages from a wearable on the list. This layer needs no broker support, so it holds even if layer 2 only denies topics.

**First boot:** with no stored list yet, the gateway accepts wearables. That matches the cloud's view at provisioning: a just-installed gateway has nothing stored, and it gets the list on its first connect.

### Outage window

A wearable revoked *during* an outage can still use an offline gateway; the gateway keeps monitoring rather than stopping. When the backlog is uploaded, ingestion compares each message's timestamp with the wearable's revocation time:
- sent before the revocation: stored normally;
- sent after it: stored as `quarantined`, not shown as a normal record.

Today ingestion rejects *all* data from a non-active wearable, so the revocation time must be recorded (new `devices.status_changed_at`) and backlog messages must be treated differently from live ones. The quarantine waits until the backlog payload is defined (`gaps.md`).

## Slices

### Slice 0 — Spike and decisions (S)
- **Mosquitto enforcement mechanism**, on Pi OS's Mosquitto version, in the container broker the CA tool's tests already use. It must stop a revoked wearable's publishes and subscriptions (required) and disconnect it (wanted). Candidates:
  1. **Generated ACL file + SIGHUP** (stock Mosquitto, no plugin): the uplink writes `topic deny #` lines for listed wearables ahead of the `pattern` lines and sends SIGHUP, which reloads the ACL. To verify: that `deny` overrides the `pattern` allow; that a connected client is checked against the new ACL on its next publish; whether it can be disconnected at all.
  2. **Dynamic security plugin:** `disableClient` disconnects the client. To verify: whether it applies to clients identified by `use_identity_as_username`, which may skip plugin authentication.
  3. **Fallback:** an auth/ACL plugin that reads the stored file, or a broker with a hook API.
- **Certificate entries:** if the mechanism sees only the username (CN), a single revoked credential cannot be enforced on the gateway while the device stays active. Record the limit: revoking one wearable credential means suspending the device until it is re-issued.
- **EMQX:** confirm the REST API key bootstrap and the retained-message storage on EMQX 6.3.2.
- **CA key identifiers:** take the open decision in `gaps.md` (replace the CA or relax the uplink's strict checking). The uplink cannot connect until it is taken.
- Record the outcome in `stack.md` and `cloud-backend.md` D16.

### Slice 1 — Cloud: list, publish, disconnect (M)
Tests: TC-C28 to TC-C31 (TC-C27 is the Pi smoke test).
- TC-C28: the list follows every registry transition, the version increases, and expired certificates drop out.
- TC-C29: a gateway receives the retained list on connect, also after EMQX restarts; another gateway cannot publish to the topic.
- TC-C30: revoking or suspending a gateway, or revoking its credential, disconnects it within 5 seconds.
- TC-C31: the gateway's reported version is stored, and a gateway behind the current version is reported as stale.

### Slice 2 — Gateway: cache and enforce (M)
Tests: TC-B05 to TC-B08, against the container broker; repeated on the Pi (H-B).
- TC-B05: a listed wearable cannot publish or subscribe, and a connected one is cut off.
- TC-B06: an older, equal or invalid list is ignored.
- TC-B07: the stored list survives a gateway restart and is enforced before the uplink reconnects.
- TC-B08: with the cloud unreachable, the stored list is still enforced and unlisted wearables keep working; on reconnect, the current list is enforced with no manual action.

### Slice 3 — Outage handling (S–M)
- Gateway clock: fit the Pi's RTC battery if the model has one, otherwise install `fake-hwclock`, so the time never jumps back after an offline reboot. Backlog records say whether the clock was synchronised.
- Cloud: `devices.status_changed_at`, and quarantine of backlog data sent after the revocation (waits for the backlog payload).
- Test TC-C32: revoke during a simulated outage, reconnect; the gateway gets the list at once, the wearable is cut off, and its data sent after the revocation is quarantined.

## Files changed

**Cloud**

| File | Change |
|---|---|
| `cloud/backend/migrations/versions/0004_revocation_sync.py` (new) | `revocation_state` (one row: `version`), `revocation_outbox` (version, created/sent times), `devices.revocation_version` (gateways), `devices.status_changed_at` |
| `cloud/backend/app/revocation.py` (new) | Builds the list; bumps the version and writes the outbox in the caller's transaction; publisher and reconciler task |
| `cloud/backend/app/emqx_api.py` (new) | REST client: retained publish, list and kick a username's clients |
| `cloud/backend/app/registry.py` | `change_device_status` and `revoke_credential`: bump the list for wearables; kick for gateways; set `status_changed_at` |
| `cloud/backend/app/broker.py` | `gateway_may`: allow subscribing to `mm/revocations/wearables`; docstring |
| `cloud/backend/app/contracts.py` | `revocation-list-v1`; optional `revocation_version` on `status-v1` |
| `cloud/backend/app/ingest.py` | Store a gateway's reported version; (Slice 3) quarantine backlog sent after the revocation |
| `cloud/backend/app/main.py` | Start and stop the reconciler with the app |
| `cloud/backend/app/settings.py`, `cloud/.env.example`, `cloud/compose.yaml`, `cloud/scripts/init-env.sh` | EMQX API URL, key and secret (generated by `init-env.sh`); passed to `api` and `emqx` |
| `cloud/emqx/emqx.conf.template`, `cloud/emqx/mm-entrypoint.sh` | API key bootstrap file; retained-message storage on disk if the spike shows it is not |
| `shared/contracts/revocation-list-v1.schema.json` (new), `status-v1.schema.json` | Generated |
| `cloud/backend/tests/unit/test_revocation.py`, `tests/integration/test_revocation.py` (new); `test_broker_rules.py`, `test_registry.py`, `test_gateway.py`, `test_contracts.py` | New tests and the changed rules |
| `cloud/README.md` | New settings; how the list is published |

**Dashboard**

| File | Change |
|---|---|
| `web/dashboard/src/api/openapi.json`, `schema.d.ts` | Regenerated (the device's `revocation_version` and the current version) |
| `web/dashboard/src/features/system/devices.tsx`, `device-detail.tsx` | Stale-list flag on a gateway |
| `web/dashboard/src/services/mock/world.ts` | Sample versions, one gateway stale |

**Gateway**

| File | Change |
|---|---|
| `gateway/uplink/revocations.py` (new, in the Iteration 4 uplink package) | Subscribe, validate, version check, atomic store, load at start |
| `gateway/uplink/enforce.py` (new) | Apply the list to Mosquitto (Slice 0 mechanism); the forwarding filter |
| `gateway/uplink/status.py` | Report `revocation_version` |
| `tools/Fixed-Gateway-Setup/setup_mosquitto.sh` | ACL layout or plugin from Slice 0; `/var/lib/medmusketeer`; permission for the uplink to signal Mosquitto |
| `tools/ca-tool/tests/test_broker_interop.py` (or the gateway's own tests) | TC-B05 to TC-B08 |

**Docs**

| File | Change |
|---|---|
| `docs/decisions/stack.md`, `cloud-backend.md` (D5, D16), `mqtt-fixed-path-topics.md`, `gaps.md` | Mechanism from Slice 0; implemented status per slice |
| `docs/testing/test_traceability.md`, `docs/testing/hardware_test_procedures.md` | TC-C28 to TC-C32, TC-B05 to TC-B08, the Pi procedure |
| `docs/changelog/` | One entry per slice |

## Exit criteria

1. Revoking or suspending a wearable makes every online gateway stop accepting its messages within 10 seconds.
2. A gateway cut off from the cloud keeps enforcing its last list and keeps serving unlisted wearables; on reconnect it enforces the current list without manual action.
3. Revoking a gateway, or its credential, disconnects it from EMQX within 5 seconds.
4. The system admin sees each gateway's list version, and stale gateways are flagged.
5. Every test has a TC ID in `test_traceability.md` and stored evidence.

## Out of scope

- Short-lived gateway certificates with automatic renewal: they need an online signing service and the Device Intermediate CA (`stack.md`). Planned for FYP-2.
- Revoking a gateway in the eyes of wearables: wearables accept any registered gateway (`stack.md`, "Gateway identity: role pin"). A revoked gateway that stays offline can keep serving wearables locally until it reconnects. A documented residual risk.
- Compromise of `ca.key`: the only remedy is replacing the CA and re-issuing every device.
- A CA tool `revoke` command: removed from the CA tool plan (2026-10-29); revocation is done through the registry API and the dashboard.

## Risks

| Risk | Mitigation |
|---|---|
| Mosquitto cannot disconnect a client identified by its certificate | Slice 0 spike first; topic denial plus the services layer still stop the data; fallback broker if neither holds |
| The database and the retained message drift apart | Outbox in the same transaction; reconciler on start and every 5 minutes |
| The gateway clock is wrong after an offline reboot | RTC or `fake-hwclock`; backlog records say whether the clock was synchronised |
| The uplink cannot connect because of the CA's missing key identifiers | Decide in Slice 0, before Slice 2 |
