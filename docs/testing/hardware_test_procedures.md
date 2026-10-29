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
is ignored by git; the committed `sdkconfig.defaults` selects `partitions.csv`, but an older local
`sdkconfig` may still select `CONFIG_PARTITION_TABLE_SINGLE_APP=y`, which has no `creds` partition.
Check that `idf.py partition-table` lists `creds` at `0x1D0000` before flashing.

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
2. Scan with the app. Expected: app shows `MM-WR-XXXXXX` (`MM-GW-` before Iteration 2) and the service UUID `7a2e0001-...`.
3. Connect; the OLED shows `ENTER PASSKEY` and six digits; enter them on the phone.
4. Send the Pi hotspot SSID/password and `broker_host` 10.42.0.1, `broker_port` 8883.
   Expected: device acknowledges; serial log shows the settings saved, Wi-Fi connected, and
   `MQTT REACHABLE` on the OLED.

## H-P07 — Reboot after provisioning (TC-P07)

Power-cycle the board without touching the phone. Expected: rejoins Wi-Fi and reaches
`MQTT REACHABLE`; the Pi sees a retained `online` on `mm/fixed/<id>/status`, and `mm/fixed/<id>/alert`
after a button press (`mosquitto_sub` on the services listener).

## H-P08 — Invalid or damaged QR code (TC-P08)

Scan (a) a QR with text `hello`, (b) `MM-WR-ABCDEF|not-a-uuid`, (c) a partly covered device QR.
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

**Blocked: the Pi is not available, and the run waits for the CA replacement** (`docs/iterations/iteration-4-revocation-sync.md`, Slice 0), so that it checks the final trust anchor and the uplink's generated ACL. It can share a session with H-B06.

The same checks run automatically against a Mosquitto container (`test_broker_interop.py`). TC-B01 already passed on the Pi on 2026-10-22 (`evidence/2026-10-22/hardware/README.md`); TC-B02 to B04 were not run because the `gw_services` password was not at hand. Use the commands recorded in `evidence/<date>/broker/broker_cases.json`, with `journalctl -u mosquitto` as the broker log. The services listener (1883) accepts only loopback, so run its subscribers on the Pi over SSH. Wearable-side clients connect to `gateway.medmusketeer.local:8883`, resolved to the Pi in `/etc/hosts`.

1. Set a new `gw_services` password on the Pi: `sudo mosquitto_passwd /etc/mosquitto/passwd gw_services`, then `sudo systemctl restart mosquitto`. Keep it in `PI_GW_SERVICES_PASS` for the session only; it is not written to the evidence.
2. **TC-B02, TC-B03** with the real CA and two registered wearables A and B: A publishes on its four own topics and receives a command on its own `command` topic (sent from the services listener); A's publish on B's alert topic is refused (`Denied PUBLISH` in the journal, nothing at the services monitor); A's subscriptions to B's command topic and to `mm/fixed/+/alert` deliver nothing.
3. **TC-B04** needs a wearable whose CN is `gw_services`. `mmca` issues only UUID names, and the real CA must not sign anything else, so use a scratch CA as in the 2026-10-22 TC-B01 run: back up `/etc/mosquitto/certs`, install a scratch CA and a gateway certificate from it, issue the `gw_services` client certificate from the scratch CA (Python `cryptography`, as `test_broker_interop.py` does), and check that it can neither read `mm/fixed/+/alert` nor publish on any `command` topic. Restore the backup and check the fingerprints of `ca.crt` and `gateway.crt` against the CA tool's records before going on.
4. Once the uplink runs (H-B06 step 1) and a wearable is listed, repeat step 2: the `%u` patterns must still work above the deny blocks the uplink writes into `/var/lib/medmusketeer/wearables.acl`.

Record any difference between the Pi configuration and the container one.

## H-W01 — Alert from the push button (TC-W01)

**Blocked: the Pi is not available.**

1. Flash the Iteration 2 firmware (button on the GPIO set in menuconfig, default 4, to GND) and provision it with the `MM-WR-` app build; wait for `MQTT REACHABLE`.
2. On the Pi: `mosquitto_sub -h 127.0.0.1 -u gw_services -P "$PI_GW_SERVICES_PASS" -v -t 'mm/fixed/+/#' | tee capture.txt`.
3. Press the button three times, at least 2 s apart. Expected: the OLED shows `ALERT SENT` with `SEQ 0`, `1`, `2`; three alerts arrive.
4. On the laptop: `cloud/backend/.venv/bin/python firmware/wearable/tools/check_capture.py capture.txt --device-id $ESP_ID`. Expected: `errors: 0`.
5. Press twice within 2 s. Expected: one alert only.

Keep `capture.txt` and the serial log as evidence.

## H-W02 — Presence and Last Will (TC-W02)

**Blocked: the Pi is not available.**

1. With the subscriber of H-W01 running, reset the board. Expected: `{"v":1,"state":"online"}` on `mm/fixed/<id>/status` after it reconnects.
2. Start a new subscriber. Expected: it receives the retained `online` at once.
3. Cut the board's power. Expected: `{"v":1,"state":"offline"}` on the same topic within about 30 s (keepalive 20 s × 1.5), and a new subscriber then gets the retained `offline`.
4. Run `check_capture.py` on the capture. Expected: `errors: 0`.

## H-W03 — Button pressed while not connected (TC-W03)

**Blocked: the Pi is not available.**

1. With the board connected, stop the broker (`sudo systemctl stop mosquitto`) and wait for `MQTT DISCONNECTED`.
2. Press the button. Expected: the OLED shows `ALERT DROPPED` / `NOT CONNECTED`; the serial log says the alert was dropped.
3. Start the broker. Expected: after the reconnect, no alert is sent until the button is pressed again; the next alert's `seq` follows the last one sent.

## H-B06 — Revocation list on the Pi (TC-B05 to TC-B08)

**Blocked until the MedMusketeer CA is replaced.** The current CA has no Subject Key Identifier, so the uplink's strict verification refuses the cloud's chain. The steps are in `docs/iterations/iteration-4-revocation-sync.md`, Slice 0.

1. Run `setup_mosquitto.sh`, then `mmca deploy`, then `setup_uplink.sh <cloud Tailscale address>`. Check that `journalctl -u medmusketeer-uplink` shows "connected to the cloud", and that `GET /admin/revocation` on the cloud no longer lists this gateway as stale.
2. With the wearable connected and sending, suspend it as the system admin (`POST /admin/devices/{id}/suspend`). Within 10 s:
   - `/var/lib/medmusketeer/wearables.acl` holds its deny block;
   - `journalctl -u mosquitto` shows "Reloading config" and `Denied PUBLISH` from it;
   - the dashboard shows no new alerts from it.
3. Stop the cloud link (e.g. `sudo tailscale down`), then reboot the Pi. Check that the wearable is still refused after the boot, while the cloud is still unreachable. Also check that `date` did not jump back (`fake-hwclock`, or the Pi 5 RTC with its battery), and that the uplink's journal says the clock is not synchronised yet.
4. With the link still down, re-activate the wearable in the cloud. Bring the link back up, and check that the uplink reconnects by itself and the wearable's alerts arrive again.

Record the times, the journal excerpts, and `ls -l /var/lib/medmusketeer` (files owned by `mosquitto`, mode 0600).
