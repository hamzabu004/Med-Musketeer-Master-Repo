# MedMusketeer ESP32-S3 Fixed-Path Client Provisioning

This ESP-IDF project implements BLE Wi-Fi onboarding and a fixed-path MQTT client for the MedMusketeer testbed. The mobile mode is a compile-time placeholder and does not start BLE or Wi-Fi services.

## Hardware

- ESP32-S3
- SH1106 128×64 I²C OLED
- Default I²C pins: SDA GPIO 8, SCL GPIO 9
- Default OLED address: `0x3C`

Change the OLED pins/address under **MedMusketeer Gateway** in `idf.py menuconfig`.

## Build mode

Fixed mode is selected by default. Run `idf.py menuconfig`, open **MedMusketeer Gateway**, and select **Mobile mode (placeholder)** to build the mobile stub. Select **Fixed gateway onboarding** to return to the implemented flow.

The project uses the ESP-IDF Component Manager for Espressif MQTT and QR code components. Open a shell with ESP-IDF 6.1 exported, then run `idf.py build`. `partitions.csv` keeps the application NVS separate from the `creds` NVS partition used by the CA Tool.

## Phone app BLE contract

The OLED QR contains two pipe-separated fields:

```text
<BLE device name>|7A2E00012B3C4D5E8F90123456789ABC
```

The second field is the canonical UUID for the provisioning GATT service (`7a2e0001-2b3c-4d5e-8f90-123456789abc`). The QR device name has the form `MM-GW-XXXXXX`; the same name appears in BLE advertising. The app should connect to this device, pair using the six-digit passkey shown on the OLED, then write one JSON document to characteristic `7a2e0002-2b3c-4d5e-8f90-123456789abc`.

Example payload:

```json
{"ssid":"GatewayWiFi","password":"example-passphrase","broker_host":"192.168.1.20","broker_port":1883}
```

The same authenticated characteristic accepts `{"action":"clear_wifi"}` to clear only the saved Wi-Fi SSID and password. The firmware preserves broker host/port, BLE bonds, and the separate TLS credentials partition, then displays `WIFI CREDENTIALS CLEARED`. Provision Wi-Fi again by sending the normal settings document. The CA Tool exposes this action as `mmca erase wifi --device-name MM-GW-XXXXXX`.

`ssid` must contain 1–32 characters. `password` may be empty for an open network or 8–63 characters. `broker_host` accepts a DNS name or IPv4 address using letters, digits, dots, and hyphens; `broker_port` must be 1–65535. Use a GATT write request and negotiate an ATT MTU of 517; the firmware accepts one JSON value up to 511 bytes.

After a valid write, Wi-Fi settings and broker endpoint are saved in ordinary application NVS. At boot the ESP reconnects automatically, while continuing to advertise for reconfiguration. Fixed-path MQTT uses `mqtts://host:port`, the CA certificate, and the wearable client certificate/private key from the read-only `creds` partition. The client synchronizes its clock with SNTP before certificate validity checks, verifies the gateway role name `gateway.medmusketeer.local`, and presents its client certificate for mTLS. “MQTT REACHABLE” appears only after clock sync, TLS verification, broker client authentication, and MQTT CONNACK succeed. The phone app can overwrite Wi-Fi settings by reconnecting and sending another valid JSON document.

After MQTT connects, the ESP publishes a test alert every random 2–5 seconds to `mm/fixed/<device_id>/alert` at QoS 1. `<device_id>` is read from the client certificate common name so it matches Mosquitto's `use_identity_as_username` ACL pattern. The payload is JSON with `device_id`, `type: "test_alert"`, `message`, and Unix `timestamp` fields. Publishing pauses while Wi-Fi or MQTT is disconnected and resumes after reconnection.

Wi-Fi credentials and TLS keys are stored in ordinary flash without flash encryption, as the FYP-1 provisioning shortcut specifies. Flashing the whole application NVS is not supported by the CA Tool; it writes only the dedicated `creds` region.

The `creds` partition uses NVS namespace `creds`, with PEM string keys `device_key`, `device_cert`, and `ca_cert`. Provision it with `mmca issue wearable` and `mmca flash --device-id <uuid>` after installing the CA Tool.
