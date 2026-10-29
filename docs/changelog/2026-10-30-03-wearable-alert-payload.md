# The wearable sends alert-payload-v1 from a push button, and its presence (Iteration 2)

- **Date:** 2026-10-30
- **Type:** code
- **Module:** M2 firmware, M3 provisioning app
- **Commits:** see `git log -- firmware/wearable apps/provisioner`

## What changed
- **Alert:** the periodic test alert is gone. One press of an external button (GPIO in menuconfig, default 4) publishes one alert-payload-v1 on `mm/fixed/<id>/alert`, QoS 1:
  - a synthetic 3 s ECG trace at 360 Hz (`lead` `SYNTH`, 200 counts/mV), ending at the press;
  - the stub screening `{"label":"abnormal","confidence":1.0,"model":"button-stub-0"}`;
  - a random UUIDv4 `msg_id` and a `seq` that restarts at 0 on boot.

  A press while MQTT is down is dropped and shown on the OLED. MQTT buffers are 4096 bytes.
- **Presence:** retained status-v1 `online` on every connect, and a Last Will `offline` (QoS 1, retained) on `mm/fixed/<id>/status`.
- **Naming:** the firmware no longer calls itself a gateway (project, files, Kconfig, log tags, tasks). The BLE/QR name is `MM-WR-XXXXXX`; the provisioning app now looks only for that prefix and says "wearable" in its texts. The NVS namespace keeps its old name so flashed boards keep their settings.
- **Checker:** `firmware/wearable/tools/check_capture.py` validates a `mosquitto_sub -v` capture with the cloud's own contract models. Its tests build `main/alert.c` on the host; CI runs them in a new `payload` job of `firmware.yml`.
- **Procedures:** new H-W01 to H-W03; H-B rewritten as numbered steps for TC-B02 to B04 on the Pi (new `gw_services` password, scratch CA for TC-B04). All blocked: the Pi is not available.
- **Scope:** ECG evaluation moved from Iteration 2 to Iteration 5.
- **Docs:** `iteration-2-wearable-alert.md` (new), `scope.md`, `gaps.md`, `stack.md`, `mqtt-fixed-path-topics.md` (also the `attested_by` wording, which now follows D1), `cloud-backend.md` D6, `test_traceability.md` (TC-W01 to W04), `hardware_test_procedures.md`, both READMEs, the `setup_mosquitto.sh` header.

## Why
The test alert broke D6 (it named the device in the payload) and could not be ingested. The cloud has accepted alert-payload-v1 and status-v1 since Iteration 3, Slice 5. With no ECG front end or model yet, a button and a synthetic segment let the rest of the path be built and tested now.

## Evidence
`docs/testing/evidence/2026-10-30/wearable/`:
- `pytest.txt`, `junit.xml`: 12 tests pass, including TC-W01 (the host-built alert passes alert-payload-v1 and fits the buffer) and TC-W04.
- `host_alert_capture.txt`, `host_alert_check.txt`: two host-built alerts, `errors: 0`.
- `firmware_size.txt`: the ESP-IDF 6.1 build for the ESP32-S3, with no compiler warnings; the app uses 66% of its 1.75 MB partition.

Not run: the provisioning app's unit tests (no Android SDK on this machine and no CI job for the app; run them in Android Studio), and every hardware procedure (the Pi is not available).
