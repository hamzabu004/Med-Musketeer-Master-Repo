<!-- Received from the model owners as ecg_1dcnn_esp32.zip on 2026-11-26 and kept as delivered.
In this repository: the C files are in ../main/ecg_model/ (ecg_classifier.cpp changed only for
C linkage, the newer schema header path and the arena log); p1_best_int8.tflite has the same bytes
as the array in p1_best_int8_ptq.h (SHA-256 fb9f1bcd…8a79e1f); the float model, report.json and
tables.md are the export's reference files. How the firmware uses it: ../README.md, "On-device model". -->

# ECG beat classifier: 1D-CNN for ESP32-S3 (TFLite Micro, INT8)

A tiny 1D-CNN (Farag 2023 architecture) that classifies each heartbeat as
**N** (normal), **S** (supraventricular ectopic) or **V** (ventricular ectopic).
It takes a single ECG lead (MLII-like) plus RR-interval features.

- Format: TensorFlow Lite, full-INT8 post-training quantisation, also given as a C array
- Size: **1,267 parameters**, **10.6 KB** flash, about 1.5 KB activations (arena 8 KB to be safe)
- Runtime: TensorFlow Lite Micro (`espressif/esp-tflite-micro`, ESP-NN kernels)

## Contents

| File | What it is |
|---|---|
| `firmware/p1_best_int8_ptq.h` | **Model as a C array** (`p1_best_int8_ptq[]`, `alignas(16) const`, stays in flash) |
| `firmware/p1_best_model_meta.h` | Input/output quantisation (scale, zero point), input indices, arena size, preprocessing constants |
| `firmware/ecg_classifier.cpp` | Ready-to-use init + classify-one-beat code |
| `model/p1_best_int8.tflite` | Same model as a raw `.tflite` file |
| `reference/p1_best_float32.tflite` | Float32 version (for PC-side checks only) |
| `reference/report.json`, `tables.md` | Full test metrics for 5 seeds, float vs INT8 |

## Performance (MIT-BIH DS2: inter-patient test set, patients never seen in training)

| | Accuracy | Macro-F1 | Se N | Se S | Se V | PPV S | PPV V |
|---|---|---|---|---|---|---|---|
| **This model (INT8, deployed)** | 97.34 | 89.45 | 98.08 | 84.49 | 94.54 | 66.75 | 95.85 |
| Same model, float (Keras) | 97.45 | 89.70 | 98.26 | 83.40 | 94.35 | 68.64 | 95.99 |
| Mean of 5 training seeds (INT8) | 97.46 | 89.76 | 98.30 | 82.38 | 94.55 | 71.23 | 94.49 |

- The INT8 model gives the same class as the float model on **99.7 %** of test beats.
- Se = sensitivity (recall), PPV = precision. Predicting "all normal" would already score 89.7 % accuracy, so read macro-F1 first.
- Seed 0 was fixed as the deploy model before any test numbers were looked at.
- Host latency is about 0.1 ms/beat; this has **not yet been measured on the ESP32**.

## Integration (ESP-IDF)

1. `idf.py add-dependency "espressif/esp-tflite-micro"`
2. Copy the three files in `firmware/` into `main/` and add `ecg_classifier.cpp` to the component sources.
3. Call `ecg_classifier_init()` once, then `ecg_classify_beat(win64, rr4, probs)` for every beat.
   The return value is 0 = N, 1 = S, 2 = V, or -1 on error.
4. Print `interp->arena_used_bytes()` once (commented line in the .cpp) and shrink the arena if needed.

The graph has 8 ops, all registered in the .cpp: CONCATENATION, CONV_2D, FULLY_CONNECTED, QUANTIZE, REDUCE_MAX, RESHAPE, SOFTMAX, TANH.
**Input 0 is the ECG and input 1 is RR.** Always use the `P1_BEST_IN_*_INDEX` macros.

## Preprocessing the device must reproduce (exactly as in training)

1. **Signal:** one ECG lead in **millivolts**, sampled at (or resampled to) **128 Hz**. No band-pass filter.
2. **R-peak detection:** this is not part of the model; the firmware needs its own detector (e.g. Pan-Tompkins).
3. **Window:** 64 samples around each R peak, `R-32 .. R+31`. The R peak is at index 32.
   `ecg_classify_beat` does the z-score and derivative itself, so pass the raw mV window.
4. **RR features** (intervals in samples at 128 Hz):
   - `pre_RR  = R[i] - R[i-1]`, `post_RR = R[i+1] - R[i]`
   - `local`  = mean of the last **80** pre_RR values (including the current one)
   - `global` = mean of the last **400** pre_RR values (including the current one)
   - `rr4 = {pre_RR/local, pre_RR/global, post_RR/local, post_RR/global}`
   - At start-up, average whatever history exists. For the very first beat use `pre_RR = post_RR`.
   - A beat can only be classified after the **next** R peak arrives (about one beat of latency). The global mean needs a 400-entry ring buffer.

## Notes / limitations

- Trained on MIT-BIH (360 Hz MLII, resampled to 128 Hz). A different front end (e.g. ADS1292 at 500 Hz) must be resampled to 128 Hz and scaled to mV.
- The INT8 RR input saturates above about 1.7 (pre_RR/local). Very long pauses are clipped, as they were during calibration.
- Only N/S/V are output. F (fusion) and Q (unclassifiable) beats are not modelled.
- Accuracy drops on short recordings, because the 80/400-beat RR means need history. On 10-second strips, S sensitivity fell sharply in our zero-shot tests.
