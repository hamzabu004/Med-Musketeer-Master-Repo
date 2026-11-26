# 2026-11-26 — ADS1292 sampler and on-device model (Iteration 5, Slices 2 and 2b)

Host and build evidence only; nothing here ran on the board (H-W04 and H-W08 are not run yet).

| File | What it shows |
|---|---|
| `build.txt` | `idf.py build` and `idf.py size` for the default configuration (ADS1292, model on): the app is 0x14fbf0 bytes, 75 % of the 0x1c0000 partition; 188 KB of 342 KB DIRAM is static, leaving 154 KB for the heap. The SYNTH front end and the model-off configuration also build. No warnings in the project's own code. |
| `pytest-ci-env.txt` | `firmware/wearable/tools` in the cloud backend's environment, as the `payload` CI job runs it: TC-W01, TC-W04, TC-W07, TC-W08 (synthetic) and TC-W09 pass; the two MIT-BIH tests are skipped there (no numpy, no database). |
| `pytest-mitdb.txt` | `test_ecg_beats.py` with the MIT-BIH Arrhythmia Database and `ai-edge-litert`. On the 22 DS2 test records, resampled 360 → 500 SPS as the ADS1292 delivers them: the firmware's detector finds 99.76 % of annotated beats with 99.74 % of its detections correct, 96.4 % within one 128 Hz sample of the annotation. The deployed INT8 model on the beats it found: 49 118 N/S/V beats, accuracy 97.45 %, macro-F1 89.78 %, Se N/S/V 98.09/84.79/95.73 %, PPV S/V 68.19/94.51 %. The model export's own report, with annotated R peaks: 97.34 % and 89.45 % (`firmware/wearable/model/tables.md`). |

The model is the one in `firmware/wearable/model/p1_best_int8.tflite`; the array compiled into the firmware (`main/ecg_model/p1_best_int8_ptq.h`) has the same SHA-256, `fb9f1bcd64a48c8f716d5cfd4b7962cb3a47b9ce2f9eface8f1d5ffab8a79e1f`. The host check runs it with LiteRT rather than TensorFlow Lite Micro, with the same quantisation as `ecg_classifier.cpp`; the inference time on the ESP32-S3 is measured in H-W08.
