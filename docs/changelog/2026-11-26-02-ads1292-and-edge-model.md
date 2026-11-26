# The wearable reads the ADS1292 and classifies beats on the device

- **Date:** 2026-11-26
- **Type:** code
- **Module:** M2 firmware
- **Commits:** pending

## What changed
- **ECG front end:** the ADS1292 replaces the AD8232, which is dropped with its menuconfig options and driver.
  - New `ecg_ads1292.c`: SPI2 at 1 MHz, 500 SPS continuous read, internal 2.42 V reference, gain 6, channel 1 (lead II) with right-leg drive and DC lead-off detection; channel 2 off. At boot the driver checks the chip ID and reads every register back.
  - `ecg_convert.c` now parses ADS1292 frames, converts codes to µV, removes the electrode offset with a 0.5 Hz DC blocker and stores int16 at 200 counts/mV, as before.
  - The pins, all free before: SCLK 12, DIN 11, DOUT 13, CS 10, DRDY 4, START 5, PWDN/RESET 6. They are in a new menuconfig menu, **ADS1292 pins**, and the lead name defaults to `II`.
  - The sampler's ring grows from 10 to 12 s, and its minute log counts lost frames.
- **On-device model:** the INT8 1D-CNN from the model owners (`ecg_1dcnn_esp32.zip`: Farag 2023 architecture, 1,267 parameters, N/S/V) runs on the wearable with TensorFlow Lite Micro (`espressif/esp-tflite-micro` ^1.4.3).
  - `firmware/wearable/model/` keeps the export as delivered; `main/ecg_model/` holds its C files.
  - New `ecg_beats.c` reproduces the training preprocessing: 500 → 128 Hz, Pan-Tompkins R peaks, the 64-sample window and the RR features.
  - New `edge_rule.c` alerts when 3 of the last 10 beats are S or V, at most once a minute; `edge_model.c` runs the pipeline on its own task.
- **Alerts:** a model alert carries the last 10 s of ECG (500 SPS, lead II) with the label `S` or `V`, its confidence and the model name. The button now sends the last 10 s too (`abnormal`, `button-0`), and the synthetic trace only before 10 s exist. The alert format (alert-payload-v1) is unchanged. The MQTT output buffer grows from 4 to 16 KB.
- **Tests:** TC-W07 is rewritten for the ADS1292; TC-W08 (beat pipeline) and TC-W09 (alert rule) are new; TC-W01 also checks a model alert. `tools/mitdb.py` reads MIT-BIH records for the optional dataset checks. Hardware procedures H-W04 and H-W08 are added.
- **Docs:** the Iteration 5 plan (D-0, D-2, D-3, D-4 and D-8 changed; D-13 to D-16 new; Slice 2b), `scope.md`, `gaps.md`, `test_traceability.md`, `hardware_test_procedures.md` and the firmware README.
- This also carries the Slice 2 work started on 2026-11-06 and not committed then: the front-end interface, the sampler, the synthetic front end and the OLED's ECG line.

## Why
The ADS1292 arrived; the product needs it, and the AD8232 was for testing only (`scope.md`). The model owners delivered the edge model, so the button no longer has to stand in for it.

The alert rule needs 3 abnormal beats of 10 because one S prediction is right only about two times in three on the test set.

## Evidence
`docs/testing/evidence/2026-11-26/firmware/`. Host tests pass: 37, plus the 2 MIT-BIH tests where the dataset is present. The firmware builds for the ESP32-S3 in all three configurations; the app uses 75 % of its partition.

On MIT-BIH DS2 the firmware's detector scores Se 99.76 % and PPV 99.74 %. The model on the beats it finds scores 97.45 % accuracy and 89.78 % macro-F1, against the export's 97.34 % and 89.45 %.

Not run on the board yet: H-W04 (rate, lost frames, noise, leads-off) and H-W08 (the model on a person, inference time, free heap).
