# MedMusketeer Gateway Setup (Android BLE Companion)

MedMusketeer Gateway Setup is a native Android application built in Kotlin with Jetpack Compose. It securely provisions Wi-Fi network credentials and MQTT broker telemetry endpoints to the **MedMusketeer ESP32-S3 Gateway** over Bluetooth Low Energy (BLE) using MITM-authenticated passkey pairing and bonded GATT communication.

---

## Firmware BLE Contract & Specifications

- **Target Device Name Pattern**: `MM-GW-XXXXXX` (where `XXXXXX` is 6 uppercase hex characters).
- **OLED QR Payload Format**:
  ```text
  MM-GW-XXXXXX|7A2E00012B3C4D5E8F90123456789ABC
  ```
  - Field 1: Device Name (`MM-GW-XXXXXX`)
  - Field 2: Provisioning Service UUID without hyphens (`7A2E00012B3C4D5E8F90123456789ABC`)
- **GATT Service UUID**: `7a2e0001-2b3c-4d5e-8f90-123456789abc`
- **GATT Configuration Characteristic UUID**: `7a2e0002-2b3c-4d5e-8f90-123456789abc`
- **Security**: Write-only characteristic requiring an encrypted, MITM-authenticated bonded connection. Firmware uses passkey display pairing: the 6-digit passkey displayed on the gateway OLED must be typed into Android's native system pairing prompt.
- **Connection Handshake**:
  1. Active BLE Low-Latency Scanning to resolve scan-response device names.
  2. GATT Connection and ATT MTU negotiation (`requestMtu(517)`).
  3. Service & Characteristic discovery (`discoverServices()`).
  4. Native bonding / MITM passkey authentication (`createBond()`).
  5. Single UTF-8 JSON write with response (`WRITE_TYPE_DEFAULT`).

### JSON Payload Schema

```json
{
  "ssid": "GatewayWiFi",
  "password": "example-passphrase",
  "broker_host": "192.168.1.20",
  "broker_port": 1883
}
```

- **Validation Rules**:
  - `ssid`: String, 1–32 characters (required).
  - `password`: String, 0 characters for open Wi-Fi network (`""`), or 8–63 characters for secured networks.
  - `broker_host`: String, 1–96 characters, restricted to ASCII letters, digits, dots, and hyphens (`^[a-zA-Z0-9.-]{1,96}$`). DNS hostnames or IPv4 text supported (IPv6 not supported).
  - `broker_port`: Integer, 1 through 65535 (default 1883).
  - **Payload Size**: Entire UTF-8 JSON string must be strictly under 512 bytes (max 511 bytes).

---

## Android Studio Build & Run Instructions

### Prerequisites
- Android Studio Ladybug (2024.2+) or newer.
- Android SDK 36 (minSdk 24).
- JDK 17 or JDK 21.
- Physical Android device with Bluetooth LE hardware and Camera (BLE scanning and passkey bonding require physical hardware; emulators cannot emulate Bluetooth LE hardware peripheral pairing).

### Build Commands
```bash
# Clean and assemble debug APK
gradle :app:assembleDebug

# Run unit and Robolectric tests
gradle :app:testDebugUnitTest
```

---

## Environment & Platform Limitations

1. **Android BLE API / Hardware**:
   - BLE scanning and GATT operations require real Bluetooth hardware. In browser-streamed Android emulators or virtualization environments without physical Bluetooth controller pass-through, scanning will not detect real BLE peripherals.
   - Android system dialog handles the passkey input prompt natively; apps are strictly prohibited by the Android OS from intercepting or auto-entering passkeys for MITM security reasons.
2. **Firmware Status Reporting**:
   - The ESP32-S3 firmware does not provide a BLE status notification characteristic. A successful GATT write confirms payload acceptance and NVS storage, but does not prove Wi-Fi association or MQTT broker connectivity. The gateway OLED display is the ultimate source of truth.
