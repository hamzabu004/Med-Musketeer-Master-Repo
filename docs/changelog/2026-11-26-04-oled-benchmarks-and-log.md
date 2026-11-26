# The OLED's benchmarks and log pages show data

- **Date:** 2026-11-26
- **Type:** code
- **Module:** M2 firmware
- **Commits:** pending

## What changed
- **Page 2, benchmarks:**
  - heap used of the internal heap, in KB;
  - the app's size of its flash partition, in MB;
  - CPU load per core over the last second;
  - the model's inference time per beat: running average and slowest since boot.
  - Current shows `NO SENSOR`, because the wearable has no current sensor.
- CPU load comes from FreeRTOS run-time stats, now on in `sdkconfig.defaults` (`CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS`, 64-bit counters). An existing `sdkconfig` keeps its old value until it is regenerated or changed in menuconfig; until then the page shows `CPU --`.
- **Page 3, log:** new `elog.c` keeps the 5 newest events, as many as fit on the page, each with its local time. The events:
  - boot; ECG or model error; leads off and on;
  - Wi-Fi connected and lost; clock synced; MQTT connected and lost;
  - new settings; Wi-Fi cleared;
  - model alerts sent or dropped (`ABNORMAL V SENT`); button alerts sent or dropped.
  - Every event also goes to the serial log. ECG request events come with the on-demand stream (Iteration 5, Slice 3).
- New menuconfig option **Time zone** (`WEARABLE_TIMEZONE`, default `PKT-5`, UTC+5) for the log's times.
- `edge_model.c` keeps the inference time per beat for page 2.

## Why
The owner asked for these readings on the benchmarks page, and for the log page to list events such as abnormal beats detected and MQTT activity, keeping as many as fit on the screen.

## Evidence
Builds for the ESP32-S3 in the default (run-time stats on), SYNTH and model-off (run-time stats off) configurations. Host tests still pass. Not run on the board yet: H-W09 steps 2 and 4.
