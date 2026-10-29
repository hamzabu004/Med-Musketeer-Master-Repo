# Iteration 4 — Revocation push and cache

- **Owner:** Hamza Tariq (M7 cloud platform, M5 gateway)
- **Status:** Slice 0 done (2026-10-29): mechanisms chosen by spike, CA replacement decided (carried out by the CA custodian, below). Slice 1 (cloud) done (2026-10-29). Slices 2 and 3 not started.
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

1. **Publishing:** the API publishes through EMQX's REST API (`POST /api/v5/publish`, `retain: true`) with an API key loaded from EMQX's `api_key.bootstrap_file`, written from `.env`. A REST publish does not go through client authorisation, so no MQTT account gets publish rights to the topic. The retainer is set to `storage_type = disc`: EMQX's default (`ram`) loses the list when the container is recreated.
2. **When:** every registry change that alters the list (a wearable's status moving into or out of suspended/revoked, revoking a certificate of a wearable that is not listed) raises `revocation_state.version` in the same transaction. After the commit, the API publishes the current list and records it as `published_version`. A reconciler task in the API publishes any unpublished version every 5 seconds, and the whole list every 5 minutes from its start. The repeat costs nothing (gateways ignore an equal version) and repairs a retained message lost with EMQX's data. (The first plan had an outbox table; one state row does the same for a single list.)
3. **Gateway disconnect:** revoking or suspending a gateway, or revoking one of its credentials, kicks its sessions through the REST API (`GET /api/v5/clients?username=…`, then `DELETE /api/v5/clients/{clientid}`). Closes the D4 "may" in `gaps.md`.
4. **Staleness:** the gateway adds `revocation_version` to its own `status-v1` message. Ingestion stores it on the gateway, and the system admin's device screens flag a gateway that is behind the current version.

### Gateway (three layers)

1. **Cache (uplink service):** subscribes to the topic on every connect (the retained message arrives at once, so reconnecting needs no sync step), validates the payload, ignores older versions, and writes `/var/lib/medmusketeer/revocations.json` atomically (temp file + rename). On start it loads the stored file before anything else.
2. **Broker:** the uplink regenerates the wearable ACL file with a `user <id>` / `topic deny #` block per listed wearable and sends Mosquitto SIGHUP. A listed wearable's publishes are refused and nothing is delivered to it, on a connection that is already open too. Its connection stays open: stock Mosquitto cannot drop it (Slice 0).
3. **Services:** the uplink does not forward, and the local classifier does not process, messages from a wearable on the list. This layer needs no broker support, so it holds even if layer 2 only denies topics.

**First boot:** with no stored list yet, the gateway accepts wearables. That matches the cloud's view at provisioning: a just-installed gateway has nothing stored, and it gets the list on its first connect.

### Outage window

A wearable revoked *during* an outage can still use an offline gateway; the gateway keeps monitoring rather than stopping. When the backlog is uploaded, ingestion compares each message's timestamp with the wearable's revocation time:
- sent before the revocation: stored normally;
- sent after it: stored as `quarantined`, not shown as a normal record.

Today ingestion rejects *all* data from a non-active wearable, so the revocation time must be recorded (new `devices.status_changed_at`) and backlog messages must be treated differently from live ones. The quarantine waits until the backlog payload is defined (`gaps.md`).

## Slices

### Slice 0 — Spike and decisions (S) — Done 2026-10-29
Scripts, raw output and broker logs: `docs/testing/evidence/2026-10-29/revocation-spike/` (README there).

**Mosquitto** (2.0.21, the Pi's version, and 2.1.2, the test image; same results on both):

| Mechanism | Open connection after revocation | New connection | Other wearables | Verdict |
|---|---|---|---|---|
| A. Generated ACL file (`user <id>` / `topic deny #`) + SIGHUP | Publishes refused (MQTT 5 PUBACK 0x87), commands no longer delivered; the connection stays open | Accepted, but publishes refused and nothing delivered | Unaffected | **Chosen** |
| B. Dynamic security plugin | `disableClient` neither drops nor refuses it | A wearable unknown to the plugin connects: the plugin never authenticates certificate identities (`use_identity_as_username`) | — | Rejected |

- Lifting the deny and reloading restores the wearable.
- **No disconnect:** stock Mosquitto cannot drop a client identified by its certificate. Accepted: the connection carries nothing, and the services layer drops its messages anyway. The firmware leaves the MQTT client id at ESP-IDF's default, so a client-id takeover is not usable either.
- **Certificate entries:** the ACL sees the username (CN) only. Revoking one credential of a wearable that stays active cannot be enforced on the gateway, so it means suspending the wearable until it is re-issued. The cloud still enforces it, because ingestion checks the device. The registry and dashboard should say so when a wearable credential is revoked.

**EMQX 6.3.2:**
- An API key from `api_key.bootstrap_file` authenticates the REST API.
- `POST /api/v5/publish` with `retain: true` is delivered although client authorisation denies every publish. A client's attempt to overwrite the topic gets PUBACK 0x87, and the retained list is unchanged.
- `GET /api/v5/clients?username=` finds a client, and `DELETE /api/v5/clients/{clientid}` disconnects it with reason 0x98 (administrative action).
- The retained message is lost when the container is recreated with the default `storage_type = ram`, and kept with `disc`.

**CA key identifiers: replace the CA** (decided 2026-10-29). The current CA (created 2026-10-13) has no Subject Key Identifier, so Python 3.13+'s strict verification, which the uplink uses, refuses its chains. It has issued one gateway (`64e33c48-…`, deployed) and one wearable (`8f0f5194-…`, flashed), and no cloud certificate yet. The custodian replaces it before Slice 2, keeping the device ids:

1. `mmca replace-ca --confirm-phrase 'REPLACE MEDMUSKETEER CA'` (the old CA is archived under `ca/archive/<time>/`).
2. `mmca issue gateway --device-id 64e33c48-5c41-4afe-8772-e937e51d67a0`, then `mmca deploy --device-id 64e33c48-5c41-4afe-8772-e937e51d67a0 --host <pi> --user pi --restart` (deploys the new `ca.crt` as well).
3. `mmca issue wearable --device-id 8f0f5194-93bf-4e1d-8e72-f96fa1f3df21`, then `mmca flash --device-id 8f0f5194-93bf-4e1d-8e72-f96fa1f3df21` with the ESP32-S3 on USB.
4. `mmca issue cloud`, then `cloud/scripts/install-emqx-certs.sh` (it also copies the new `ca.crt`).
5. Check: `openssl x509 -in ~/medmusketeer-ca/ca/ca.crt -noout -ext subjectKeyIdentifier` prints an identifier, and the wearable reaches the Pi's broker again.
6. Where these devices are in a cloud registry: add each new fingerprint printed by `mmca issue` as a credential, then revoke the old one.

### Slice 1 — Cloud: list, publish, disconnect (M) — Done 2026-10-29
Tests: TC-C28 to TC-C31 (TC-C27 is the Pi smoke test); `tests/integration/test_revocation.py` (API and database, EMQX faked) and `test_revocation_stack.py` (full stack).
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
| `cloud/backend/migrations/versions/0004_revocation_sync.py` (new) | `revocation_state` (one row: `version`, `published_version`, `published_at`), `devices.revocation_version` (gateways), `devices.status_changed_at` |
| `cloud/backend/app/revocation.py` (new) | Builds the list in one snapshot; bumps the version in the caller's transaction; publisher, reconciler task and gateway disconnect |
| `cloud/backend/app/emqx_api.py` (new) | REST client: retained publish, list and kick a username's clients |
| `cloud/backend/app/registry.py` | `change_device_status` and `revoke_credential`: bump the list for wearables; kick for gateways; set `status_changed_at` |
| `cloud/backend/app/broker.py` | `gateway_may`: allow subscribing to `mm/revocations/wearables`; docstring |
| `cloud/backend/app/contracts.py` | `revocation-list-v1`; optional `revocation_version` on `status-v1` |
| `cloud/backend/app/ingest.py` | Store a gateway's reported version; (Slice 3) quarantine backlog sent after the revocation |
| `cloud/backend/app/main.py` | Start and stop the reconciler with the app |
| `cloud/backend/app/settings.py`, `cloud/.env.example`, `cloud/compose.yaml`, `cloud/scripts/init-env.sh` | EMQX API URL, key and secret (generated by `init-env.sh`); passed to `api` and `emqx` |
| `cloud/emqx/emqx.conf.template`, `cloud/emqx/mm-entrypoint.sh` | `api_key.bootstrap_file` written from the environment; `retainer.backend.storage_type = disc` |
| `shared/contracts/revocation-list-v1.schema.json` (new), `status-v1.schema.json` | Generated |
| `cloud/backend/tests/integration/test_revocation.py`, `test_revocation_stack.py` (new); `test_broker_rules.py`, `test_contracts.py`, `test_access.py`, `test_schema.py`, `conftest.py`, `tests/mqtt.py` | New tests, the changed rules, the new endpoint's matrix row, the new table |
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
| `gateway/uplink/enforce.py` (new) | Regenerate the wearable ACL file atomically and send Mosquitto SIGHUP; the forwarding filter |
| `gateway/uplink/status.py` | Report `revocation_version` |
| `tools/Fixed-Gateway-Setup/setup_mosquitto.sh` | The wearable ACL becomes a generated file (the patterns plus deny blocks) the uplink may write; `/var/lib/medmusketeer`; permission for the uplink to reload Mosquitto |
| `tools/ca-tool/tests/test_broker_interop.py` (or the gateway's own tests) | TC-B05 to TC-B08 |

**Docs**

| File | Change |
|---|---|
| `docs/decisions/stack.md`, `cloud-backend.md` (D5, D16), `mqtt-fixed-path-topics.md`, `gaps.md` | Mechanism from Slice 0; implemented status per slice |
| `docs/testing/test_traceability.md`, `docs/testing/hardware_test_procedures.md` | TC-C28 to TC-C32, TC-B05 to TC-B08, the Pi procedure |
| `docs/changelog/` | One entry per slice |

## Exit criteria

1. Revoking or suspending a wearable makes every online gateway refuse its messages and stop delivering to it within 10 seconds (its connection may stay open).
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
| Mosquitto cannot disconnect a client identified by its certificate (confirmed in Slice 0) | Accepted: topic denial plus the services layer stop its data; the open connection carries nothing |
| The database and the retained message drift apart | Outbox in the same transaction; reconciler on start and every 5 minutes |
| The gateway clock is wrong after an offline reboot | RTC or `fake-hwclock`; backlog records say whether the clock was synchronised |
| The uplink cannot connect because of the CA's missing key identifiers | CA replacement decided in Slice 0; carried out before Slice 2 |
