#pragma once

#include <stddef.h>
#include <stdint.h>

#define ALERT_FS_HZ 360        /* the synthetic fallback trace */
#define ALERT_N_SAMPLES 1080   /* 3 s */
#define ALERT_SEGMENT_S 10     /* a real segment: the last 10 s of ECG */

/* An alert's ECG segment and screening result. */
typedef struct {
    const int16_t *samples; /* counts at 200 counts/mV */
    size_t n_samples;
    uint16_t fs_hz;
    const char *lead;
    int64_t start_us;       /* wall-clock time of the first sample, microseconds since the epoch */
    const char *label;      /* "S", "V" from the model; "abnormal" for the button */
    double confidence;
    const char *model;
} alert_segment_t;

/* Builds one alert-payload-v1 (shared/contracts/alert-payload-v1.schema.json). With a segment,
 * the alert carries it; with NULL, a synthetic 3 s trace at 360 Hz (lead SYNTH) that ends now,
 * screened by the button stub (for a button press before 10 s of ECG exist).
 * Returns a string to release with cJSON_free, or NULL. */
char *alert_build(uint64_t seq, const alert_segment_t *segment);
