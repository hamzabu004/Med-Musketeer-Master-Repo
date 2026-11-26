#pragma once

/* Beat extraction for the on-device classifier, with no ESP-IDF dependency so the host test
 * (TC-W08) can build it. It reproduces the model's training preprocessing
 * (ecg_model/p1_best_model_meta.h):
 *
 *  1. 500 SPS int16 counts -> millivolts -> 128 Hz, by a polyphase windowed-sinc resampler
 *     (32/125; the training data went 360 -> 128 Hz with resample_poly). No band-pass.
 *  2. R peaks by Pan-Tompkins at 128 Hz: 5-15 Hz band-pass, derivative, square, 150 ms moving
 *     window, adaptive thresholds with search-back and a T-wave check. The R peak is then placed
 *     on the largest deflection of the 128 Hz signal near the detected QRS.
 *  3. Each beat is emitted once the next R peak is known: the 64-sample window R-32 .. R+31 in mV
 *     and the RR features {pre/local, pre/global, post/local, post/global}, where local and global
 *     are the means of the last 80 and 400 pre-RR intervals, the current one included.
 *
 * A sample taken with leads off resets the detector and the RR history; detection starts again
 * after a 2 s learning period of clean signal. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define BEATS_FS_IN 500
#define BEATS_FS 128
#define BEATS_WIN 64
#define BEATS_WIN_BEFORE 32
#define BEATS_RR_LOCAL 80
#define BEATS_RR_GLOBAL 400

#define BEATS_RS_L 32  /* 500 * 32 / 125 = 128 */
#define BEATS_RS_M 125
#define BEATS_RS_HALF 16 /* taps each side, at the input rate */
#define BEATS_IN_RING 64 /* power of two, > 2 * BEATS_RS_HALF */
#define BEATS_RING 512   /* 128 Hz signal history: 4 s, power of two */
#define BEATS_SLOPE_RING 32 /* squared-derivative history, > the 150 ms window; power of two */
#define BEATS_PENDING 4

typedef struct {
    uint64_t r;        /* R peak, as a 128 Hz sample index since ecg_beats_init */
    float win[BEATS_WIN]; /* mV, R at index BEATS_WIN_BEFORE */
    float rr[4];       /* pre/local, pre/global, post/local, post/global */
    float pre_rr_s;    /* the RR interval before this beat, in seconds */
} ecg_beat_t;

typedef struct {
    float a1, a2, b0, b1, b2, z1, z2;
} ecg_biquad_t;

typedef struct {
    float counts_per_mv;
    float poly[BEATS_RS_L][2 * BEATS_RS_HALF];

    /* 500 Hz input history */
    float in[BEATS_IN_RING];
    uint8_t in_off[BEATS_IN_RING];
    uint64_t n_in;
    uint64_t n_out; /* 128 Hz samples produced */

    /* 128 Hz history */
    float x[BEATS_RING];             /* mV */
    float mwi[3];                    /* moving-window integral at k-2, k-1, k */
    float slope[BEATS_SLOPE_RING];   /* squared derivative */

    /* detector */
    ecg_biquad_t hp, lp;
    float deriv_hist[4];
    float sq_hist[BEATS_SLOPE_RING];
    float mwi_sum;
    uint64_t clean_since; /* first 128 Hz index of the current clean (leads on) stretch */
    bool learned;
    float spki, npki;
    float learn_max, learn_sum;
    uint32_t learn_n;
    uint64_t last_qrs;   /* MWI peak index of the last QRS; UINT64_MAX = none */
    float last_qrs_slope;
    uint64_t best_idx;   /* the largest sub-threshold MWI peak since the last QRS (search-back) */
    float best_val;
    float best_slope;
    uint64_t wait_since; /* start of the current wait for a QRS (the stale-threshold timer) */
    float rr_avg;        /* mean of the last 8 RR intervals, in 128 Hz samples; 0 = unknown */
    uint32_t rr_avg_n;

    /* beats */
    uint64_t r_prev;     /* the R peak before pending[0]; UINT64_MAX = none */
    uint64_t pending[BEATS_PENDING];
    size_t n_pending;
    uint16_t rr_hist[BEATS_RR_GLOBAL];
    size_t rr_count, rr_next;
} ecg_beats_t;

void ecg_beats_init(ecg_beats_t *b, float counts_per_mv);

/* Feeds n 500 Hz samples with their leads-off flags (off may be NULL). Writes up to max finished
 * beats to out and returns how many. A call with n up to 500 yields at most a few beats. */
size_t ecg_beats_push(ecg_beats_t *b, const int16_t *counts, const uint8_t *off, size_t n,
                      ecg_beat_t *out, size_t max);

/* Clears the detector and RR history (for example after samples were lost). */
void ecg_beats_reset(ecg_beats_t *b);
