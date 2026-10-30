# Iteration 2 — The wearable's alert, its presence, and the ACL check on the Pi

- **Owner:** Hamza Tariq (M2 firmware, M3 provisioning app, M5 gateway)
- **Status:** Slices 1 to 4 done (2026-10-30): built, compiled for the ESP32-S3, and the alert checked on the host against the cloud's contract. Every hardware check (H-W01 to H-W03, H-B for TC-B02 to B04) is **blocked: the Pi is not available**. The H-B run also waits for the CA replacement (`iteration-4-revocation-sync.md`, Slice 0).
- **Scope change (2026-10-30):** the ECG evaluation that `scope.md` listed under Iteration 2 moved to Iteration 5. The classifier code is still in its own repository (`scope.md`, M4).
- **Depends on:** `cloud-backend.md` D6 (alert-payload-v1), D15 (status-v1), D16 (a wearable's status carries no `revocation_version`); `mqtt-fixed-path-topics.md`; `shared/contracts/`

## Goal

The wearable sends what the cloud already accepts. Its alert follows alert-payload-v1 instead of the test alert of Iteration 1, and its presence is a retained `status` with a Last Will. There is no ECG front end or edge model yet, so a push button stands in for the model and the segment is synthetic. The broker's per-wearable ACL denials, so far shown only on a container broker, are repeated on the Pi.

## Decisions (2026-10-30)

| Question | Decision |
|---|---|
| What triggers an alert | An external push button (GPIO in menuconfig, default 4, active low). The 2–5 s timer is removed |
| ECG samples | A synthetic trace: Gaussian P, QRS and T waves at 72 bpm, 200 counts/mV, the 3 s ending at the press |
| Segment | 360 Hz × 1080 samples (3 s), `lead` `SYNTH` |
| `screening` | Fixed stub `{"label":"abnormal","confidence":1.0,"model":"button-stub-0"}`, so the cloud and dashboard show that no model ran |
| `msg_id`, `seq` | Random UUIDv4; `seq` counts from 0 and restarts at 0 on every boot (not stored in NVS) |
| Press while MQTT is down | Dropped, shown on the OLED; buffering waits for the wearable buffer design (`gaps.md`) |
| Presence | Retained `{"v":1,"state":"online"}` on connect; Last Will `{"v":1,"state":"offline"}`, QoS 1, retained. No `mode_switch` reason until the mode switch exists |
| Naming | The firmware stops calling itself a gateway. BLE/QR name `MM-WR-XXXXXX` (was `MM-GW-`); the app accepts only the new prefix. The NVS namespace stays `gateway` so a flashed board keeps its settings |
| Hardware checks | Wait for the Pi. TC-B02 to B04 run after the CA replacement; TC-B04 uses a scratch CA, as in the 2026-10-22 TC-B01 run |

## Slices

### Slice 1 — Rename the firmware's "gateway" to "wearable" (S) — Done 2026-10-30
Project `medmusketeer_wearable`; `main/fixed_path.{c,h}`; Kconfig menu "MedMusketeer Wearable" with `WEARABLE_*` options; log tags and task names. The provisioning app looks for `MM-WR-` and its texts say wearable; its Kotlin type names (`GatewayDevice`, …) were left as they are.

### Slice 2 — Alert payload and push button (M) — Done 2026-10-30
`main/alert.c` builds alert-payload-v1. The button's interrupt wakes the alert task, which debounces (50 ms), publishes at QoS 1 and ignores presses for 2 s. MQTT buffers are 4096 bytes (an alert is about 3.2 KB).

### Slice 3 — status-v1 and the Last Will (S) — Done 2026-10-30
The `online` message is queued from the MQTT event handler (`esp_mqtt_client_enqueue`), not published from it.

### Slice 4 — Message checker and procedures (S) — Done 2026-10-30
`firmware/wearable/tools/check_capture.py` checks a `mosquitto_sub -v` capture with the cloud's own models plus per-device rules (seq, `msg_id`, times). Its tests build `main/alert.c` on the host and check the output (TC-W01, TC-W04), locally and in the `payload` job of `firmware.yml`. H-W01 to H-W03 are written in `hardware_test_procedures.md`.

### Slice 5 — ACL denials on the Pi — Blocked (Pi not available; after the CA replacement)
H-B in `hardware_test_procedures.md` is now a numbered procedure: a new `gw_services` password set over SSH, TC-B02 and B03 with the real CA, TC-B04 with a scratch CA restored afterwards, and TC-B02/B03 again above the uplink's deny blocks. TC-B01 already passed on the Pi on 2026-10-22.

## Exit criteria

1. The firmware builds for the ESP32-S3 in CI. **Met.**
2. The firmware's alert passes alert-payload-v1 (TC-W01, host). **Met.**
3. On the Pi, button alerts and the wearable's status pass `check_capture.py` (H-W01, H-W02), and a press while disconnected sends nothing (H-W03). **Blocked.**
4. TC-B02 to B04 pass on the Pi (H-B). **Blocked.**

The iteration is done when 3 and 4 are met.

## Out of scope

- ECG evaluation, the edge model, ECG acquisition (AD8232 or ADS1292) → Iteration 5
- The gateway forwarding alerts and wearable status to the cloud → the uplink bridge (Iteration 4)
- `telemetry`, `command`, `command_ack`, the mode switch, buffering while disconnected

## Risks

| Risk | Handling |
|---|---|
| A 3.2 KB QoS 1 publish over the wearable's link | Buffers set to 4096; confirmed by H-W01 |
| No NTP on the Pi hotspot without internet (`gaps.md`) | `segment_start` uses the same SNTP clock that TLS already needs |
| Old app with new firmware (or the reverse) cannot pair | Ship and install both together; the app test refuses `MM-GW-` names |
| The Pi run of TC-B04 swaps the broker's CA | Back up first, restore and check fingerprints before continuing (H-B step 3) |
