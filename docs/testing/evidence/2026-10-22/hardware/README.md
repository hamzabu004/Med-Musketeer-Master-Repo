# Hardware test records, 2026-10-22

Board: ESP32-S3 (QFN56) rev v0.2, MAC `b8:1f:3f:da:7e:ec`, 16 MB flash, USB-Serial/JTAG on
`/dev/ttyACM0`, firmware as found on the board (app built 16 Oct 2026, ESP-IDF v6.1; BLE name
`MM-GW-DA7EEC`, wearable CN `8f0f5194-93bf-4e1d-8e72-f96fa1f3df21`) until the D1 fix was flashed
for the last TC-P07 run. Host: Fedora laptop, esptool 5.x from the CA-tool venv,
BlueZ with `bleak`. Gateway: Raspberry Pi hotspot `f-gateway-AP` (10.42.0.1), uplink through the
laptop's `local-share` Ethernet and the campus Wi-Fi.

TC-P03, TC-A07, and the erase runs used a scratch CA (`MedMusketeer Scratch Test CA`, 30-day
validity), not the project CA. The board's first 2 MB were backed up before and restored after;
see `flash_backup_restore.txt`. Scripts used are in `scripts/`.

| ID | Result | Evidence | Observed |
|---|---|---|---|
| TC-P03 | Pass | `p03.json`, `p03.txt`, `p03_boot_serial.txt` | `mmca flash` checked the chip (ESP32-S3, MAC recorded), wrote `creds` at 0x1D0000 (196,608 bytes) and verified the read-back hash in 5.4 s; the local key file was removed and the device marked flashed; audit `issue`, `flash` success. A separate read of the partition contained the device and CA certificates. On boot the firmware logged `Loaded TLS credentials from the read-only creds partition` and the alert topic with the new CN. |
| TC-A07 (missing partition) | Pass | `a07.json`, `a07.txt` | With a partition table without `creds` written to the board, `mmca flash` stopped with `No 'creds' partition found; flash firmware containing it first`; the key was kept, the device not marked flashed, and the `creds` region hash unchanged. Original table restored and verified identical. Wrong-chip case not run (no non-S3 board). |
| Erase `network` | Pass | `erase-network.*` | Only `nvs` (0x9000) erased; reads back blank; next boot: TLS credentials loaded, no saved Wi-Fi, BLE advertising. |
| Erase `tls` | Pass | `erase-tls.*` | Only `creds` (0x1D0000) erased; reads back blank; next boot: `No credentials namespace in creds partition: ESP_ERR_NVS_NOT_FOUND`. |
| Erase `all` | Pass | `erase-all.*` | Both partitions erased and blank; next boot: no credentials, no saved Wi-Fi, advertising. |
| TC-P07 (fixed firmware, D1) | Pass | `p07_fixed_fw_serial.txt`, `p07_fixed_fw_pi_capture.txt`, `p07_pi_broker_log.txt`, `firmware_fixed_build.txt` | App rebuilt with the D1 fix and flashed at 0x10000 only (partition table byte-identical to the board's; settings and credentials untouched). After a reset with no input: joined `f-gateway-AP`, IP at 14.1 s, `MQTT broker accepted CONNECT (CONNACK received)` at 15.7 s, then alerts on `mm/fixed/8f0f5194-.../alert` every 2–5 s (21 between 19.1 s and 86.5 s). The Pi broker logged `New client connected from 10.42.0.239 ... u'8f0f5194-93bf-4e1d-8e72-f96fa1f3df21'` (mutual TLS on the real Pi, CN as username). The clock was already valid at this boot (no DNS or NTP in the capture), so this run does not exercise the new clock-sync path. After a USB power cycle (clock unset) the broker logged a new connection 10 s after the power loss (`1792666688`–`690`); no serial log of that boot was taken. A controlled test with NTP blocked was dropped. |
| TC-P07 (rerun after testbed fixes, original firmware) | Partial (Wi-Fi pass, MQTT fail) | `p07_after_fix_serial.txt`, `p07_after_fix_pi_capture.txt` | With the Pi online and its hotspot fixed (D3, D4), the board rejoined `f-gateway-AP` and had IP 10.42.0.239 at 13.7 s, then logged `System clock is not synchronized; refusing TLS connection` at 23.8 s. The Pi capture shows why: the board resolved `pool.ntp.org` through 10.42.0.1 to 103.167.159.26 and sent NTP there; no reply came (that server also times out from the laptop). SNTP retried the same server 30 s later, but the firmware had already given up after its single 10 s wait (D1). |
| TC-P07 (first run) | Partial (Wi-Fi pass, MQTT fail) | `p07_reboot_serial.txt` | After a hard reset with no input the board loaded its saved settings and joined `f-gateway-AP` (WPA3-SAE), IP 10.42.0.239 at 13.7 s. At 23.7 s it logged `System clock is not synchronized; refusing TLS connection`; it did not retry during a further 75 s. Cause: the Pi had no internet. It reached the laptop (192.168.50.1) and its DNS, but no ICMP, TCP 443, or NTP got past the laptop, which itself had full access; the Pi's own clock was unsynchronised and three days behind. The laptop runs Docker 29, which sets the kernel FORWARD policy to DROP, the usual cause of NetworkManager connection sharing failing on Fedora (not confirmed: listing the rules needs root). The firmware also waits 10 s once and does not retry. See defects D1 and D3. |
| TC-A08 (unknown host) | Pass | `a08-reject.json`, `a08-reject.txt` | `mmca deploy` to the Pi with an empty known_hosts showed `SHA256:ZEjqK2vKu8Rbfk3yV/ZKERrb8m14WzCMiKrk1WeyHU0` (the Pi's key, matching the entry saved for 10.42.0.1) and asked for approval; on `n` it stopped with `Unknown SSH host was not approved`, saved nothing, and the Pi's certificate files were unchanged. |
| TC-A08 (changed host key) | Pass | `a08-changed.json`, `a08-changed.txt` | With known_hosts holding a different ed25519 key for the Pi, deploy stopped with `SSH host key mismatch for 192.168.50.188; refusing connection`; nothing uploaded. |
| TC-P04 | Pass | `p04.json`, `p04.txt`, `pi_cert_backup_restore.txt` | Scratch gateway certificate deployed to the Pi with `--restart`: the tool listed the existing files and asked before backing up and overwriting, installed `ca.crt`, `gateway.crt`, `gateway.key` as `root:mosquitto 0640` in a `0750` directory, verified them remotely, restarted Mosquitto (active), and logged `deploy` / success. The SHA-256 of each file on the Pi equals the local file. Afterwards the original files were restored from a backup taken first (hashes identical), the tool's `.bak` copies removed, Mosquitto restarted, and the board reconnected with its own identity. |
| TC-B01 on the Pi | Pass | `b01_pi_clients.txt`, `b01_pi_broker_log.txt` | With the scratch CA on the Pi (during TC-P04): a scratch wearable connected over mutual TLS as `u'<its CN>'` and published its alert; a wearable from another CA (`certificate verify failed`), a client with no certificate (`peer did not return a certificate`), and a client connecting by IP rather than the role name (`bad certificate` raised by the client) were refused. The board, whose certificate is from the project CA, was refused for the same period (17 connection attempts, none accepted) and reconnected once the original CA was restored. Pi broker: Mosquitto 2.0.21. |
| TC-B02 to TC-B04 on the Pi | Not run | — | The Pi's services listener needs the `gw_services` password, which was not available. The Pi's two-listener configuration and both ACL files match the container configuration used for TC-B02 to TC-B04 (`../broker/`). |
| TC-P10 | Pass | `ble_p10_p09_p12.json`, `ble_session2_serial.txt` | Laptop paired with the passkey shown on the OLED (typed by the tester), then in the same connection sent six invalid documents: empty SSID, 5-character password, `bad host!`, port 70000, missing fields, and `not json`. Each got ATT error 0x0D (Invalid Attribute Value Length) in about 0.1 s, the board logged `Rejected invalid BLE provisioning payload` six times, and MQTT alerts continued throughout. A valid document with a wrong Wi-Fi password was accepted; the board then failed Wi-Fi authentication ten times over 45 s while staying reachable over BLE, accepted the corrected settings over the same link, rejoined, and reached CONNACK 5 s later. After a reset it booted with the saved settings and reached CONNACK at 6.7 s (`ble_after_tests_boot_serial.txt`). |
| TC-P09 | Pass (limited) | `ble_p10_p09_p12.json`, `ble_session2_serial.txt` | A complete settings write was sent and the link closed immediately. The write completed before the disconnect (accepted in 0.1 s): the board applied the full settings, re-advertised, rejoined Wi-Fi, and reached CONNACK. A settings document fits in one ATT write, so the board receives all of it or nothing; the drop did not land inside a write. |
| TC-P05 | Pass | Report Figure 7.1 (tester's photos), `p05_p06_prep_erase_network.txt`, `p05_p06_app_serial.txt` | Network settings erased with `mmca erase esp network` for the board's real identity (MAC checked, `nvs` erased and verified blank); the board booted to `Waiting for BLE Wi-Fi provisioning` with QR `MM-GW-DA7EEC\|7A2E0001...`. The Android application scanned it, searched for `MM-GW-DA7EEC`, and found it at `B8:1F:3F:DA:7E:EE`; pairing began (`BLE passkey displayed on OLED` at 54 s). |
| TC-P06 (application) | Pass | Report Figure 7.3 (tester's photos), `p05_p06_app_serial.txt`, `p06_app_pi_broker_log.txt` | After pairing with the OLED passkey, the application sent SSID `f-gateway-AP`, the hotspot password, and broker 10.42.0.1:8883, and showed `Settings Accepted by Gateway`. Board: joined the hotspot at 257.3 s, IP at 258.5 s, `MQTT broker accepted CONNECT` at 260.1 s, then alerts. Pi broker: `New client connected from 10.42.0.239 ... u'8f0f5194-93bf-4e1d-8e72-f96fa1f3df21'`. The confirmation screen calls the broker connection unencrypted `mqtt://`, which is wrong (O2). |
| TC-P08 | Pass | Report Figure 7.1 (tester's screenshot) | A QR code whose payload has one field instead of two was refused: `Invalid QR structure: expected exactly 2 fields separated by '\|' (got 1)`. |
| TC-P12 (wrong passkey) | Pass | `ble_p10_p09_p12.json`, `ble_session2_serial.txt` | With the laptop bond removed, pairing with a wrong passkey typed by the tester failed (`org.bluez.Error.AuthenticationFailed`, 9.5 s); a write of `{"ssid":"P12-WRONG-PASSKEY",...}` straight after was refused (ATT 0x0E). The laptop holds no bond, and the probe SSID is absent from the board's `nvs` partition. |
| TC-P12 (no pairing) | Pass | `p12_unpaired.md`, `p12_unpaired_serial.txt` | A write to the settings characteristic from an unpaired laptop did not reach the application: pairing was demanded, the board showed a passkey, none was entered, and the board dropped the link after 30 s. The `nvs` partition read back byte-identical to the backup; the test SSID is absent. |

## Defects found

- **D1 — MQTT never starts when the first clock sync fails.** One server, one 10 s wait, no retry;
  the OLED stays on `CLOCK SYNC FAILED`. The fixed path also depends on the internet for time
  this way. The 10 s wait also ran inside the Wi-Fi/IP event handler, blocking the default event
  loop. **Fixed 2026-10-22** in `firmware/wearable/main/fixed_gateway.c` (not yet committed): three
  SNTP servers (`time.google.com`, `pool.ntp.org`, `time.cloudflare.com`), and the wait moved to a
  `gateway_clock` task that keeps waiting while SNTP retries, then starts MQTT. Built with ESP-IDF
  v6.1 and `scripts/sdkconfig.defaults.used`. Still open: a local time source on the Pi, so the
  fixed path does not need the internet for time.
- **D2 — Fresh builds have no `creds` partition.** `sdkconfig` is git-ignored and no
  `sdkconfig.defaults` is committed; the local `sdkconfig` selects the single-app table. The board
  itself has the custom table, so it was built with a different configuration.

- **D3 — Testbed: the Pi's uplink through the laptop forwards nothing.** Test-environment issue,
  not a project defect. With no internet the Pi's clock also drifts, which would make it reject
  newly issued certificates as not yet valid.

- **D4 — Testbed: duplicate DHCP server on the Pi hotspot.** A standalone `dnsmasq.service`
  (`/etc/dnsmasq.d/esp-ap.conf`, serving DHCP on `wlan0`) competed with NetworkManager's shared-mode
  dnsmasq for 10.42.0.1. It had failed 650+ times since boot; at 11:34:26 BST it won, and the
  hotspot then failed every few seconds with `ip-config-unavailable`, so the board could not
  authenticate. Fixed 2026-10-22: the service was disabled and the file renamed to
  `esp-ap.conf.disabled`; the hotspot then stayed connected.

## Not run

TC-P05, TC-P06, TC-P08 (phone app). Dropped from scope: the controlled TC-P07 variant with NTP
blocked, the TC-A07 wrong-chip case on hardware (covered by the mocked unit test), TC-B02 to TC-B04
on the Pi (covered in the container), and the old TC-A09 and TC-A11 (removed from the report; the old TC-A10 is now TC-A09).

## Observation

- **O1 — Writes over a reused BLE bond never completed from the laptop.** After pairing in one
  connection and reconnecting later with the stored bond (both sides had it; the board's `nvs` held
  the laptop's address), every write timed out without reaching the firmware, and BlueZ then
  answered `In Progress` to any write on that characteristic, even on new connections
  (`ble_attempt1_stuck_writes.json`, `ble_session_serial.txt`). Removing the device from BlueZ and
  pairing and writing in the same connection worked. Not determined whether the board (security
  re-establishment) or BlueZ is at fault; worth checking with the phone app, which reconnects with a
  stored bond.
- **O2 — Application text.** The confirmation screen says the board makes an unencrypted `mqtt://`
  connection; the firmware uses mutual TLS (`mqtts://`).
- **O3 — Generic rejection reason (FR-P10).** Any invalid settings document shows only
  `INVALID SETTINGS` / `CHECK APP VALUES` (or `PAYLOAD SIZE`) on the OLED and returns ATT 0x0D; the
  failing field is not reported (`fixed_gateway.c`, `config_characteristic_access`).
