#pragma once

/* C interface to ecg_classifier.cpp (the 1D-CNN from model/, TFLite Micro, INT8). */

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ECG_CLASS_N 0
#define ECG_CLASS_S 1
#define ECG_CLASS_V 2
#define ECG_MODEL_NAME "farag-1dcnn-p1best-int8-s0"

/* Once at boot. False if the model does not load or its tensors do not fit the arena. */
bool ecg_classifier_init(void);

/* win64: 64 samples in mV at 128 Hz, R at index 32. rr4: {pre/local, pre/global, post/local,
 * post/global}. probs (may be NULL) gets P(N), P(S), P(V). Returns the class, or -1. */
int ecg_classify_beat(const float win64[64], const float rr4[4], float probs[3]);

#ifdef __cplusplus
}
#endif
