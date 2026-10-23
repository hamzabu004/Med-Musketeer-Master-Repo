# Android BLE provisioning app committed

- **Date:** 2026-10-23
- **Type:** code
- **Module:** M3 provisioning app
- **Commits:** 6bc0602

## What changed
Added `apps/provisioner/`: a Kotlin/Jetpack Compose app that scans the wearable's QR code, bonds over BLE with passkey pairing, and writes the Wi-Fi and MQTT broker settings to the provisioning characteristic. Includes unit tests.

## Why
It is the phone app used in hardware procedures TC-P05 to TC-P10, and it existed only locally.

## Evidence
Hardware procedure records in `docs/testing/evidence/2026-10-22/hardware/`.

## Known issues
- No root `build.gradle.kts`, no Gradle wrapper, and no `.env.example`, so it probably does not build from a fresh clone.
- Generator leftovers: `metadata.json`, an unused `ic_gateway_icon_1791912950729.jpg`, the package name `com.example`.
- The README calls the target an "ESP32-S3 Gateway" and uses broker port 1883; the target is the wearable and the broker port is 8883.
