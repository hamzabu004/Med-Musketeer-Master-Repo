# MedMusketeer — Fixed-Path MQTT Topic Structure (Local Broker + Gateway Uplink)

Companion to `stack.md` (section "MQTT topic structure"). Status markers follow that file: **Decided** / **Proposed** / **Open** / **Implemented**. The wearable topics and the Mosquitto ACLs (sections 1 and 4) are **Implemented** and tested on a container broker with the Pi's configuration; the wearable publishes `alert` and `status` (Iteration 2), not yet `telemetry` or `command_ack`. The gateway-side services (section 2) are **Proposed** and not built yet; the uplink (section 3) exists for the revocation list only (Iteration 4).

Last updated: 2026-10-30

## Base scheme (Decided)

`mm/{path}/{device_id}/{msg_type}`, with `path ∈ {fixed, mobile}`.

This document covers the **fixed path** only. `{id}` is the wearable's canonical UUID, which is also its mTLS cert CN.

**Additions to `msg_type`** (fixed path, **Decided**): `status`, `command_ack`. These fill the LWT-topic and command-acknowledgement-topic items.

## 1. Wearable (ESP32-S3) ↔ local broker (Mosquitto on the Pi)

| Direction | Topic | Purpose | Notes |
|---|---|---|---|
| **Subscribe** | `mm/fixed/{id}/command` | Authenticated on-demand commands | The **only** subscription the wearable needs |
| Publish | `mm/fixed/{id}/telemetry` | ECG chunks of an on-demand recording | **Decided:** continuous streaming happens only on demand — after a doctor's request command, for the duration of that recording. Outside an on-demand recording nothing is published here (ADR-1) |
| Publish | `mm/fixed/{id}/alert` | TinyDL-triggered alert with the triggering ECG segment | The main data flow, QoS 1, alert-payload-v1. Until the edge model exists, a push button sends one alert with a synthetic segment and the stub screening `button-stub-0` (Iteration 2) |
| Publish | `mm/fixed/{id}/status` | Presence | Retained, QoS 1, status-v1. `online` on connect; LWT publishes `offline` (**Implemented**, Iteration 2) |
| Publish | `mm/fixed/{id}/command_ack` | Command acknowledgement | |

- **No `heartbeat` topic on the fixed path.** MQTT keepalive + LWT carry presence (see `stack.md`, liveness section).
- **Why a `status` topic:** Mosquitto has no per-client connect/disconnect events (only aggregate `$SYS` counters). A retained `status` topic plus LWT is how the gateway learns wearable presence.
- **Mode switch:** before the button switches paths, the wearable publishes `offline` with `reason: "mode_switch"`, then disconnects cleanly. This lets the cloud read it as a mode change, not a failure.
- **No `result` subscription.** The wearable does not consume classification results; keeping its ACL minimal reduces attack surface.

## 2. Gateway services ↔ local broker

Gateway services connect over a loopback listener with their own local credentials. They are not wearables.

| Direction | Topic | Service |
|---|---|---|
| Subscribe | `mm/fixed/+/telemetry` | Classifier, IDS feature extractor |
| Subscribe | `mm/fixed/+/alert` | Classifier, alert forwarder |
| Subscribe | `mm/fixed/+/status` | Presence service |
| Subscribe | `mm/fixed/+/command_ack` | Uplink bridge |
| Publish | `mm/fixed/{id}/command` | Uplink bridge (after receiving the command from EMQX) |
| Publish (optional) | `mm/fixed/{id}/result` | Classifier → bridge, only if split into separate processes |

## 3. Gateway ↔ EMQX (private-CA mTLS listener)

Separate connection from the local broker.

| Direction | Topic |
|---|---|
| Publish | `mm/fixed/{wearable_id}/{telemetry,alert,result}` (forwarded unchanged; the cloud takes `attested_by` from the gateway's EMQX username, `cloud-backend.md` D1) |
| Publish | `mm/gateway/{gw_id}/ids_event` |
| Publish | `mm/gateway/{gw_id}/status` (gateway's own presence + forwarded wearable presence) |
| Publish | `mm/gateway/{gw_id}/backlog` (post-outage upload) |
| Subscribe | `mm/fixed/{wearable_id}/command` for its assigned wearables |
| Subscribe | `mm/revocations/wearables` (retained list of revoked wearables, published only by the cloud; `cloud-backend.md` D16, Iteration 4) |

- Wearable presence forwarded upward is **gateway-attested**.
- If the gateway drops, the cloud marks its wearables **unknown/stale**, not offline, until the gateway reconnects and uploads its backlog.
- `mm/gateway/...` is the already-Proposed gateway-event topic extension.

## 4. Mosquitto ACL (Implemented)

Requires `per_listener_settings true`, and on the wearable listener `require_certificate true` and `use_identity_as_username true`, so `%u` is the cert CN. A wearable cannot publish to or subscribe on another device's topics.

**Two listeners, two ACL files.** The wearable mTLS listener (port 8883) and the gateway-services loopback listener (127.0.0.1:1883) each get their own ACL file. In a single combined file, a wearable cert whose CN happened to match a services username could inherit the services' permissions; separate files per listener close that off. Anything not listed is denied.

`wearables.acl` (mTLS listener; username = CN = device_id). Since Iteration 4 this file is `/var/lib/medmusketeer/wearables.acl`, owned by `mosquitto` with mode 0600. It is generated by the gateway uplink (`gateway/uplink`): these patterns, then a `user <device id>` / `topic deny #` block for each wearable on the revocation list (`cloud-backend.md` D16). `setup_mosquitto.sh` writes only the first version.

```
pattern write mm/fixed/%u/telemetry
pattern write mm/fixed/%u/alert
pattern write mm/fixed/%u/status
pattern write mm/fixed/%u/command_ack
pattern read  mm/fixed/%u/command
```

`services.acl` (loopback listener):

```
user gw_services
topic read  mm/fixed/+/telemetry
topic read  mm/fixed/+/alert
topic read  mm/fixed/+/status
topic read  mm/fixed/+/command_ack
topic write mm/fixed/+/command
topic write mm/fixed/+/result
```

**Verification status:** the CN-to-username mapping has been observed on the Pi. The denials above were verified on a container broker running the Pi's configuration (TC-B01 to TC-B04, `tools/ca-tool/tests/test_broker_interop.py`, evidence in `docs/testing/evidence/2026-10-22/broker/`); TC-B01 (authentication) passed on the Pi on 2026-10-22; repeating the denials (TC-B02 to B04) on the Pi is part of Iteration 2 and waits for the Pi and the CA replacement. An unauthorized publish is dropped silently for MQTT 3.1.1 clients, so judge by what a monitor subscriber or the broker log shows. Setup script: `tools/Fixed-Gateway-Setup/setup_mosquitto.sh`.

## 5. QoS / retain (Proposed starting point, still Open; `alert` QoS 1 is implemented)

| Topic | QoS | Retain |
|---|---|---|
| `telemetry` | TBD | No |
| `alert` | 1 | No |
| `command` | 1 | No |
| `command_ack` | 1 | No |
| `status` | 1 | Yes |

**Benchmark note:** whatever QoS is chosen for `telemetry` and `alert`, hold it constant across both paths. QoS directly affects latency and would confound the path comparison.

## 6. Open items

- Final QoS for `telemetry` and the other topics.
- Fixed-path payload format: the alert, status and IDS-event payloads are decided and implemented in the cloud (`cloud-backend.md` D6, D15; schemas in `shared/contracts/`); the wearable firmware sends alert-payload-v1 and status-v1 since Iteration 2 (360 Hz, 3 s segments); the gateway still has to forward them. There is no envelope on this path (mTLS protects the hop). A recording will also carry its command id. The send timestamp is benchmark-only and never used in a security decision.
- How an on-demand stream starts and stops: request command fields, fixed duration vs explicit stop command, and how `command_ack` reports it.
- Gateway discovery by the wearable (currently the broker host/port is provisioned over BLE; the Pi hotspot is `10.42.0.1`).
- Cloud-side ACL: observe vs enforce which wearables a gateway may subscribe to for `command`.
- Verify the ACL denials on the actual Pi (CN-to-username already observed there).
