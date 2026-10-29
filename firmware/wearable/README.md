# MedMusketeer ESP32-S3 Wearable

This ESP-IDF project is the wearable's firmware: BLE Wi-Fi onboarding and a fixed-path MQTT client for the MedMusketeer testbed. The mobile mode is a compile-time placeholder and does not start BLE or Wi-Fi services.

## Hardware

- ESP32-S3
- SH1106 128×64 I²C OLED
- Default I²C pins: SDA GPIO 8, SCL GPIO 9
- Default OLED address: `0x3C`
- Alert push button between GPIO 4 and GND (active low; the internal pull-up is used)

Change the OLED pins/address and the button GPIO under **MedMusketeer Wearable** in `idf.py menuconfig`.

## Build mode

Fixed mode is selected by default. Run `idf.py menuconfig`, open **MedMusketeer Wearable**, and select **Mobile mode (placeholder)** to build the mobile stub. Select **Fixed path (local gateway)** to return to the implemented flow.

The project uses the ESP-IDF Component Manager for Espressif MQTT and QR code components. Open a shell with ESP-IDF 6.1 exported, then run `idf.py build`. `partitions.csv` keeps the application NVS separate from the `creds` NVS partition used by the CA Tool.

## Phone app BLE contract

The OLED QR contains two pipe-separated fields:

```text
<BLE device name>|7A2E00012B3C4D5E8F90123456789ABC
```

The second field is the canonical UUID for the provisioning GATT service (`7a2e0001-2b3c-4d5e-8f90-123456789abc`). The QR device name has the form `MM-WR-XXXXXX` (`MM-GW-` before Iteration 2; the provisioning app accepts only the new prefix); the same name appears in BLE advertising. The app should connect to this device, pair using the six-digit passkey shown on the OLED, then write one JSON document to characteristic `7a2e0002-2b3c-4d5e-8f90-123456789abc`.

Example payload:

```json
{"ssid":"GatewayWiFi","password":"example-passphrase","broker_host":"192.168.1.20","broker_port":1883}
```

The same authenticated characteristic accepts `{"action":"clear_wifi"}` to clear only the saved Wi-Fi SSID and password. The firmware preserves broker host/port, BLE bonds, and the separate TLS credentials partition, then displays `WIFI CREDENTIALS CLEARED`. Provision Wi-Fi again by sending the normal settings document. To clear the network settings and BLE bonds over USB instead, use `mmca erase esp network`.

`ssid` must contain 1–32 characters. `password` may be empty for an open network or 8–63 characters. `broker_host` accepts a DNS name or IPv4 address using letters, digits, dots, and hyphens; `broker_port` must be 1–65535. Use a GATT write request and negotiate an ATT MTU of 517; the firmware accepts one JSON value up to 511 bytes.

After a valid write, Wi-Fi settings and broker endpoint are saved in ordinary application NVS. At boot the ESP reconnects automatically, while continuing to advertise for reconfiguration. Fixed-path MQTT uses `mqtts://host:port`, the CA certificate, and the wearable client certificate/private key from the read-only `creds` partition. The client synchronizes its clock with SNTP before certificate validity checks, verifies the gateway role name `gateway.medmusketeer.local`, and presents its client certificate for mTLS. “MQTT REACHABLE” appears only after clock sync, TLS verification, broker client authentication, and MQTT CONNACK succeed. The phone app can overwrite Wi-Fi settings by reconnecting and sending another valid JSON document.

### Messages

`<device_id>` below is the client certificate's common name, so it matches Mosquitto's `use_identity_as_username` ACL pattern. The payloads follow the contracts in `shared/contracts/`.

- **Presence** on `mm/fixed/<device_id>/status`, QoS 1, retained (status-v1). `{"v":1,"state":"online"}` is published on every connect. The same topic with `{"v":1,"state":"offline"}` is the connection's Last Will, which the broker publishes when the keepalive (20 s) runs out.
- **Alert** on `mm/fixed/<device_id>/alert`, QoS 1 (alert-payload-v1). One press of the alert button sends one alert. There is no ECG front end or on-device model yet (Iteration 5), so the alert carries a synthetic 3 s ECG trace at 360 Hz (`lead` `SYNTH`, 200 counts/mV) ending at the press, and the fixed screening `{"label":"abnormal","confidence":1.0,"model":"button-stub-0"}`. `msg_id` is a random UUID; `seq` counts alerts from 0 and restarts at 0 on every boot. A press while MQTT is down is dropped and the OLED shows `ALERT DROPPED`; after a publish it shows `ALERT SENT` and the seq. Presses within 2 s of the last one are ignored.

The MQTT buffers are 4096 bytes; one alert is about 3.2 KB.

`tools/check_capture.py` checks a `mosquitto_sub -v` capture of these messages with the cloud's own contract models; its tests (`tools/test_check_capture.py`) also build `main/alert.c` on the host and check its output (H-W01 to H-W03 and TC-W01, TC-W04 in `docs/testing/`).

Wi-Fi credentials and TLS keys are stored in ordinary flash without flash encryption, as the FYP-1 provisioning shortcut specifies. Flashing the whole application NVS is not supported by the CA Tool; it writes only the dedicated `creds` region.

The `creds` partition uses NVS namespace `creds`, with PEM string keys `device_key`, `device_cert`, and `ca_cert`. Provision it with `mmca issue wearable` and `mmca flash --device-id <uuid>` after installing the CA Tool.
