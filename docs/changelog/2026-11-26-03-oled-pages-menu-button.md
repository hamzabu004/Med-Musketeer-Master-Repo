# Numbered OLED pages and a menu button on the wearable

- **Date:** 2026-11-26
- **Type:** code
- **Module:** M2 firmware
- **Commits:** 3f2f4f3 (firmware), d3f5d6c (docs)

## What changed
- A second push button, **menu**, between GPIO 14 and GND (menuconfig `WEARABLE_MENU_BUTTON_GPIO`). Each press shows the next OLED page.
- New `ui.c` owns the OLED. Once Wi-Fi is set up, the home view is four numbered pages:
  1. **ECG:** the live trace, with the heart rate and last beat class from the on-device model in the header.
  2. **Benchmarks:** empty for now.
  3. **Log:** empty for now.
  4. **Gateway:** Wi-Fi network, signal, IP address, the latest connection message and the broker address.
- Every page header shows the page number and a link circle (filled: connected to the gateway's broker).
- Alert results and connection messages now appear over the current page for 3 s; the menu button dismisses one early. Pairing screens (QR code, passkey) stay until pairing ends and ignore the menu button.
- When a phone disconnects after Wi-Fi is set up, the wearable returns to its pages; it used to show the pairing QR code again.
- The connected screen (`WIFI CONNECTED` / `MQTT REACHABLE` / ECG state) and the debug option **Show a live ECG trace on the OLED** are gone: page 1 is the trace and page 4 the connection.
- `display.c` draws the page header and the trace page, and its font gains `%`, `+` and `>`. The model alert's `V BEATS 87%` showed `?` for the `%` before.
- `edge_model.c` keeps the heart rate (mean of the last 8 RR intervals), the last beat class and the beat counts for page 1.

## Why
The owner asked for a menu button and numbered screens: ECG, benchmarks, log and gateway connectivity, with benchmarks and log left empty for now.

## Evidence
Builds for the ESP32-S3 in the default, SYNTH and model-off configurations. Host tests still pass (37, with 2 skipped without MIT-BIH). Not run on the board yet: H-W09 in `docs/testing/hardware_test_procedures.md`.
