# Hardware test procedures (FYP-1 provisioning chain)

These cases need the ESP32-S3 wearable board, the phone with the provisioning app, and the
Raspberry Pi gateway. Use a scratch CA (`mmca --root ~/mm-test-ca ...`) and throwaway device IDs.

For every run, record in `docs/testing/evidence/<date>/hardware/<ID>.md`:

```text
ID:            Date/time:            Tester:
Firmware:      commit + `idf.py --version`      App: version/commit      Pi OS + mosquitto -h
Device ID:     Board MAC:
Steps run:     (as below, note any deviation)
Observed:      (what happened, exact messages)
Evidence:      file names of serial log (idf.py monitor > file), screenshots, broker log extract
Result:        Pass / Fail / Blocked — reason
```

Before starting: the firmware build must contain the `creds` partition. `firmware/wearable/sdkconfig`
is ignored by git and no `sdkconfig.defaults` is committed; the local copy selects
`CONFIG_PARTITION_TABLE_SINGLE_APP=y`, which has no `creds` partition. Check that
`idf.py partition-table` lists `creds` at `0x1D0000` before flashing.

## H-P03 — Flash wearable credentials over serial (TC-P03)

1. `mmca issue wearable --device-id $ESP_ID`, then `mmca flash --device-id $ESP_ID --port /dev/ttyACM0`.
2. Expected: `Flash verified on ... at 0x1D0000`; `issued/$ESP_ID/device.key` removed; `meta.json` has
   `"flashed": true` and the chip MAC; `mmca audit --device-id $ESP_ID` shows `flash` / `success`.
3. Boot the board with `idf.py monitor`; the log must not show `Cannot initialize creds partition`.

## H-A07 — Flash a board without a creds partition (TC-A07)

1. Flash a firmware built with the single-app table, then run `mmca flash` for a new wearable ID.
2. Expected: `No 'creds' partition found ...`; nothing written; `device.key` still present; `flashed` false.

## H-P04 — Deploy gateway credentials over SSH (TC-P04)

1. `mmca issue gateway --device-id $GW_ID`, then `mmca deploy --device-id $GW_ID --host <pi> --user pi`.
2. On the Pi: `sudo ls -l /etc/mosquitto/certs` — each file `root:mosquitto` mode 0640, directory 0750. `sudo openssl x509 -in gateway.crt -noout -fingerprint -sha256` must equal
   the fingerprint printed by `issue`.

## H-A08 — Unknown and changed SSH host key (TC-A08)

The CA tool uses `~/.ssh/known_hosts`; back it up first.

1. `ssh-keygen -R <pi>`, deploy, answer `n`. Expected: deployment stops; known_hosts has no entry for
   the Pi. Repeat, compare the shown fingerprint with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`
   on the Pi, answer `y`: the entry is saved.
2. Replace the saved key with another key (or regenerate the Pi host keys), deploy again.
   Expected: hard stop on host-key mismatch; no file uploaded.

## H-P05, H-P06 — QR, pairing, and settings transfer (TC-P05, TC-P06)

1. Erase network settings (`mmca erase esp network ...`), boot: the OLED shows the QR code.
2. Scan with the app. Expected: app shows `MM-GW-XXXXXX` and the service UUID `7a2e0001-...`.
3. Connect; the OLED shows `ENTER PASSKEY` and six digits; enter them on the phone.
4. Send the Pi hotspot SSID/password and `broker_host` 10.42.0.1, `broker_port` 8883.
   Expected: device acknowledges; serial log shows the settings saved, Wi-Fi connected, and
   `MQTT REACHABLE` on the OLED.

## H-P07 — Reboot after provisioning (TC-P07)

Power-cycle the board without touching the phone. Expected: rejoins Wi-Fi and reaches
`MQTT REACHABLE`; the Pi sees `mm/fixed/<id>/alert` again (`mosquitto_sub` on the services listener).

## H-P08 — Invalid or damaged QR code (TC-P08)

Scan (a) a QR with text `hello`, (b) `MM-GW-ABCDEF|not-a-uuid`, (c) a partly covered device QR.
Expected: the app refuses each and states why; no BLE connection is attempted.

## H-P09 — BLE link lost during transfer (TC-P09)

Start a write and switch the phone's Bluetooth off at once (or move out of range). Expected: the
serial log shows no saved settings; the device still advertises; the retry succeeds.

## H-P10 — Invalid or incomplete settings (TC-P10)

Write each document with a generic BLE client (e.g. nRF Connect) after pairing:
`{"ssid":"","password":"12345678","broker_host":"10.42.0.1","broker_port":8883}`,
`{"ssid":"x","password":"short","broker_host":"10.42.0.1","broker_port":8883}`,
`{"ssid":"x","password":"12345678","broker_host":"bad host!","broker_port":8883}`,
`{"ssid":"x","password":"12345678","broker_host":"10.42.0.1","broker_port":70000}`, and `not json`.
Expected: each write fails with an ATT error; the log shows `Rejected invalid BLE provisioning payload`;
the previous settings stay in effect. Then a wrong Wi-Fi password: device fails to join, stays
reachable over BLE, and accepts corrected settings.

## H-P12 — Write without pairing or with a wrong passkey (TC-P12)

1. Remove the bond on the phone. With nRF Connect, connect and write to `7a2e0002-...` without pairing.
   Expected: insufficient-authentication error; nothing stored.
2. Pair and enter a wrong passkey. Expected: pairing fails; the write is refused.

## H-B — Broker interop on the Pi (TC-B01 to TC-B04)

The same checks ran automatically against a Mosquitto container (`test_broker_interop.py`). To repeat
them on the Pi, use the Pi's `mosquitto.conf`, `wearables.acl`, and `services.acl`, and the commands
recorded in `evidence/<date>/broker/broker_cases.json`, with `journalctl -u mosquitto` as the broker
log. Record any difference between the Pi configuration and the container one.
