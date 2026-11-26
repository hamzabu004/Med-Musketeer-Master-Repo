# MedMusketeer ESP32-S3 Wearable

This ESP-IDF project is the wearable's firmware: BLE Wi-Fi onboarding and a fixed-path MQTT client for the MedMusketeer testbed. The mobile mode is a compile-time placeholder and does not start BLE or Wi-Fi services.

## Hardware

- ESP32-S3
- SH1106 128×64 I²C OLED
- Default I²C pins: SDA GPIO 9, SCL GPIO 3
- Default OLED address: `0x3C`
- Alert push button between GPIO 21 and GND (active low; the internal pull-up is used)
- Menu push button between GPIO 14 and GND (active low; the internal pull-up is used): steps through the OLED pages
- ADS1292 ECG front end on SPI2, 3.3 V, internal clock (CLKSEL high on the module):

  | ADS1292 | ESP32-S3 |
  |---|---|
  | SCLK | GPIO 12 |
  | DIN (MOSI) | GPIO 11 |
  | DOUT (MISO) | GPIO 13 |
  | CS | GPIO 10 |
  | DRDY | GPIO 4 |
  | START | GPIO 5 |
  | PWDN/RESET | GPIO 6 |

  GPIO 10–13 are SPI2's IO MUX pins. The pins avoid the strapping pins (0, 3, 45, 46), USB (19, 20), the flash and octal PSRAM (26–37) and UART0 (43, 44).
- Electrodes, lead II on channel 1: IN1N on the right arm, IN1P on the left leg, RLD on the right leg. Channel 2 is powered down.

Change the OLED pins/address, the button GPIOs, the ADS1292 pins and the ECG options under **MedMusketeer Wearable** in `idf.py menuconfig`.

## ECG sampling

The wearable samples ECG from boot, whether or not anything is recording (Iteration 5, D-3):

- **ADS1292** (the default front end, `ecg_ads1292.c`): channel 1 at 500 SPS in continuous read mode, internal 2.42 V reference, PGA gain 6, right-leg drive from channel 1. At boot the driver resets the chip, checks its ID (0x53) and reads every register back, so wrong wiring shows as `ECG ERROR` and a log line rather than as noise. DRDY's falling edge wakes the sampler, which reads one 9-byte frame per sample at 1 MHz. A code is turned into microvolts (`code × 2 × 2.42 V / 6 / 2²⁴`, about 0.048 µV per code), the electrode offset is removed by a 0.5 Hz DC blocker, and the result is stored as int16 at 200 counts per mV (5 µV per count). A sample is marked leads-off when the chip's DC lead-off comparators flag IN1P or IN1N. The ADS1292 has no FIFO, so a frame not read before the next DRDY is lost; the sampler's minute log counts those.
- **Synthetic trace** (`ecg_synth.c`): a generated 72 bpm trace at 500 SPS, for bench runs without electrodes. Select it under **ECG front end**.

The sampler task (`ecg_sampler.c`, priority 6) keeps the last 12 s (6000 samples and their leads-off flags) in a ring. A sample's time is its index divided by the rate, added to a wall-clock anchor that is set once SNTP has set the clock and is refreshed every minute. Once a minute the sampler logs the samples it received, how many were taken with leads off and how many were lost, for example `ecg_sampler: ADS1292: 30000 samples in 60.003 s = 499.98 SPS; 0 with leads off; 0 lost`; this is the measurement for H-W04.

Page 1 of the OLED (below) shows the sampler's state: the live trace, `LEADS OFF` in its header (a lead was off within the last second), or `ECG ERROR` (the front end did not start, or sent no samples for a second). If the front end fails, the rest of the firmware still runs.

## OLED pages

Once Wi-Fi is set up, the OLED shows numbered pages (`ui.c`). Each press of the menu button shows the next one, wrapping from 4 to 1:

| Page | Shows |
|---|---|
| `1/4 ECG` | The last 2.56 s of ECG, redrawn 10 times a second and scaled to fit. The header adds the heart rate and the last beat's class from the on-device model (`72 BPM N`), or `LEADS OFF`. |
| `2/4 BENCHMARKS` | `RAM` heap used of the total internal heap, in KB (the rest is free); `FLASH` the app's size of its partition, in MB; `CPU` the load on each core over the last second (100 % minus the idle task's share; needs `CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS`, in `sdkconfig.defaults`, else `CPU --`); `INFER` the model's time per beat in µs, a running average and the slowest since boot; `CURRENT NO SENSOR` (the wearable has no current sensor). |
| `3/4 LOG` | The 5 newest events, newest first, as `HH:MM EVENT` in local time (menuconfig **Time zone**, default UTC+5), or `--:--` before the clock is set: `BOOT`, `ECG ERROR`, `MODEL ERROR`, `LEADS OFF` / `LEADS ON`, `WIFI CONNECTED` / `WIFI LOST`, `CLOCK SYNCED`, `MQTT CONNECTED` / `MQTT LOST`, `NEW SETTINGS`, `WIFI CLEARED`, `ABNORMAL V SENT` (or `S`, or `DROP` when it could not be sent), `BTN ALERT SENT` / `DROP`. Every event also goes to the serial log (tag `event`). The on-demand ECG requests add theirs when Slice 3 is built. |
| `4/4 GATEWAY` | The Wi-Fi network, its signal in dBm, the IP address, the latest connection message (`MQTT REACHABLE`, `SYNCING CLOCK...`, `MQTT DISCONNECTED`, …) and the gateway's broker address. |

Every page's header ends with a small circle: filled when the wearable is connected to the gateway's broker, hollow when not. The wearable starts on page 1.

Alert results and connection messages appear over the current page for 3 s; a press of the menu button dismisses one early. The pairing screens (the QR code, the passkey, `PHONE PAIRED`) stay until pairing ends, and the menu button does nothing while they are shown. Before Wi-Fi is set up there are no pages, only the pairing screens.

`tools/test_ecg_convert.py` (TC-W07) builds `main/ecg_convert.c` on the host and checks the frame parsing, the lead-off bits, the conversion to microvolts, the DC blocker, the int16 counts and the leads-off count.

## On-device model

The wearable classifies every beat as N (normal), S (supraventricular ectopic) or V (ventricular ectopic) with the INT8 1D-CNN in `model/` (Farag 2023 architecture, 1,267 parameters, 10.6 KB; trained on MIT-BIH MLII; see `model/README.md`), run by TensorFlow Lite Micro (`espressif/esp-tflite-micro`). Turn it off with **On-device beat classifier** in menuconfig.

1. `ecg_beats.c` reproduces the model's training preprocessing: the 500 SPS samples are resampled to 128 Hz (polyphase, 32/125), R peaks are found with Pan-Tompkins (5–15 Hz band-pass, derivative, square, 150 ms window, adaptive thresholds with search-back and a T-wave check), and each beat gets the 64-sample window around its R peak in mV and the RR features `{pre/local, pre/global, post/local, post/global}` (means of the last 80 and 400 RR intervals). A beat is ready once the next R peak is found, about one beat later. A sample with leads off restarts detection, which needs 2.5 s of clean signal to learn its thresholds again.
2. `main/ecg_model/ecg_classifier.cpp` (from the model export) z-scores and differentiates the window, quantises both inputs and runs the model, in under a millisecond per beat on the host; the ESP32-S3 time is logged as `slowest inference`.
3. `edge_rule.c` raises an alert when at least 3 of the last 10 beats are S or V, at most once every 60 s (menuconfig **Alert rule** options). The alert's label is the more frequent of S and V, and its confidence the mean probability of that class.

`edge_model.c` runs these steps on a task at priority 3 and logs a summary once a minute: beats per class, mean heart rate, the slowest inference, and the free heap.

Checked on the host (`tools/test_ecg_beats.py`): with the MIT-BIH test records (DS2) resampled to 500 SPS, the detector finds 99.76 % of the annotated beats with 99.74 % of its detections correct, 96 % of R peaks within one 128 Hz sample of the annotation. The model on the beats this pipeline finds scores 97.45 % accuracy and 89.78 % macro-F1, against 97.34 % and 89.45 % in the export's report with annotated R peaks. Those two tests need numpy, scipy, `ai_edge_litert` and the database (`MM_MITDB_DIR`); without them they are skipped. The synthetic tests (TC-W08) and the alert rule's tests (TC-W09) need only gcc.

## Build mode

Fixed mode is selected by default. Run `idf.py menuconfig`, open **MedMusketeer Wearable**, and select **Mobile mode (placeholder)** to build the mobile stub. Select **Fixed path (local gateway)** to return to the implemented flow.

The project uses the ESP-IDF Component Manager for Espressif MQTT, QR code and TensorFlow Lite Micro components. Open a shell with ESP-IDF 6.1 exported, then run `idf.py build`. `partitions.csv` keeps the application NVS separate from the `creds` NVS partition used by the CA Tool.

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
- **Alert** on `mm/fixed/<device_id>/alert`, QoS 1 (alert-payload-v1). Two things send one:
  - **the on-device model**, when its rule is met: the last 10 s of ECG (5000 samples at 500 SPS, `lead` `II`, 200 counts/mV) and the screening `{"label":"V" or "S","confidence":…,"model":"farag-1dcnn-p1best-int8-s0"}`. The OLED shows `ECG ALERT SENT`, the label and confidence, and the seq.
  - **the alert button**, as a manual alert: the last 10 s of ECG with the screening `{"label":"abnormal","confidence":1.0,"model":"button-0"}`. Until 10 s of ECG exist (or with the sampler in error), a press sends the old synthetic 3 s trace at 360 Hz (`lead` `SYNTH`) with `"model":"button-stub-0"` instead. Presses within 2 s of the last one are ignored.

  `msg_id` is a random UUID; `seq` counts alerts from 0 and restarts at 0 on every boot. An alert while MQTT is down is dropped and the OLED shows `ALERT DROPPED`. The result stays for 3 s over the current page.

The MQTT input buffer is 4096 bytes and the output buffer 16 KB: an alert with a 10 s segment is about 13.8 KB, the synthetic one about 3.2 KB.

`tools/check_capture.py` checks a `mosquitto_sub -v` capture of these messages with the cloud's own contract models; its tests (`tools/test_check_capture.py`) also build `main/alert.c` on the host and check its output (H-W01 to H-W03 and TC-W01, TC-W04 in `docs/testing/`).

Wi-Fi credentials and TLS keys are stored in ordinary flash without flash encryption, as the FYP-1 provisioning shortcut specifies. Flashing the whole application NVS is not supported by the CA Tool; it writes only the dedicated `creds` region.

The `creds` partition uses NVS namespace `creds`, with PEM string keys `device_key`, `device_cert`, and `ca_cert`. Provision it with `mmca issue wearable` and `mmca flash --device-id <uuid>` after installing the CA Tool.
