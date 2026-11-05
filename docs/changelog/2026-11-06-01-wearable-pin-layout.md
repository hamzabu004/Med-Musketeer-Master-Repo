# The wearable's new pin layout, with the AD8232 wired

- **Date:** 2026-11-06
- **Type:** hardware
- **Module:** M2 firmware
- **Commits:** ac7e96c (pin layout, AD8232 options, this entry); merged in b8e75ab (PR #15)

## What changed
- The wearable was rewired and the AD8232 ECG module added for testing. The menuconfig defaults in `firmware/wearable/main/Kconfig.projbuild` follow the new wiring:

  | Signal | Old GPIO | New GPIO |
  |---|---|---|
  | OLED SDA | 8 | 9 |
  | OLED SCL | 9 | 3 |
  | Alert button (to GND) | 4 | 21 |
  | AD8232 OUTPUT | — | 2 |
  | AD8232 LO+ | — | 15 |
  | AD8232 LO− | — | 38 |
  | AD8232 SDN | — | 5 |

- Four new menuconfig options hold the AD8232 pins: `WEARABLE_ECG_OUTPUT_GPIO`, `WEARABLE_ECG_LO_PLUS_GPIO`, `WEARABLE_ECG_LO_MINUS_GPIO` and `WEARABLE_ECG_SDN_GPIO`. The OUTPUT option accepts only GPIO 1–10 (ADC1). The firmware does not read the AD8232 yet; ECG acquisition is Iteration 5.
- The wearable README's Hardware section lists the new pins.

## Why
The first AD8232 wiring had two problems:
- OUTPUT was on GPIO 42, which has no ADC on the ESP32-S3. It moved to GPIO 2, an ADC1 pin. ADC2 (GPIO 11–20) was avoided because it is shared with Wi-Fi, which the wearable keeps on.
- LO− was on GPIO 37. On modules with octal PSRAM, GPIO 35–37 are wired to the PSRAM inside the module. LO− moved to GPIO 38.

Firmware built for the old pins could not reach the OLED after the rewiring. `display_init()` then failed and the wearable restarted about once a second.

The AD8232 is for testing only; the product needs the ADS1292 (`scope.md`), which connects over SPI and will need its own pins.

## Evidence
Checked on the bench; serial logs were read in the session but not saved:
- A temporary pin-check program (not committed) read the button as released, both leads-off pins high with no electrodes attached, and a drifting ADC value on GPIO 2.
- A temporary OLED test (not committed) found the SH1106 at `0x3C` on SDA 9 / SCL 3. Writes failed once the display turned on, and both bus lines then stayed low. That pointed to the OLED losing power, and its wires were then re-seated. The test was not re-run; the rebuilt firmware below drew the screen.
- With the rebuilt firmware, the wearable booted once with no abort in 30 s. It drew its BLE QR code, joined `f-gateway-AP`, synchronised its clock and got CONNACK from the gateway broker.

Not checked: an alert press on GPIO 21.
