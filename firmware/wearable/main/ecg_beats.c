#include "ecg_beats.h"

#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif
#include <string.h>

#define MASK (BEATS_RING - 1)
#define IN_MASK (BEATS_IN_RING - 1)
#define SLOPE_MASK (BEATS_SLOPE_RING - 1)
#define NONE UINT64_MAX

#define RS_CUTOFF 0.115f /* cycles per input sample: 57.5 Hz, under the 64 Hz output Nyquist */
#define MWI_W 19         /* 150 ms at 128 Hz */
#define SETTLE 64        /* 0.5 s for the filters after a reset, not used for learning */
#define LEARN 256        /* 2 s of thresholds learning */
#define REFRACTORY 26    /* 200 ms */
#define T_WAVE 46        /* 360 ms: a peak closer than this may be a T wave */
#define STALE 384        /* 3 s with no QRS: thresholds are halved */
#define R_SEARCH_FROM 30 /* the R peak is searched 30 .. 1 samples before the MWI peak */
#define R_SEARCH_TO 1

static void biquad_design(ecg_biquad_t *f, float fc, float fs, bool highpass)
{
    const float w0 = 2.0f * (float)M_PI * fc / fs;
    const float c = cosf(w0), alpha = sinf(w0) / (2.0f * 0.70710678f);
    const float a0 = 1.0f + alpha;
    if (highpass) {
        f->b0 = (1.0f + c) / 2.0f / a0;
        f->b1 = -(1.0f + c) / a0;
    } else {
        f->b0 = (1.0f - c) / 2.0f / a0;
        f->b1 = (1.0f - c) / a0;
    }
    f->b2 = f->b0;
    f->a1 = -2.0f * c / a0;
    f->a2 = (1.0f - alpha) / a0;
    f->z1 = f->z2 = 0.0f;
}

static float biquad(ecg_biquad_t *f, float x)
{
    const float y = f->b0 * x + f->z1;
    f->z1 = f->b1 * x - f->a1 * y + f->z2;
    f->z2 = f->b2 * x - f->a2 * y;
    return y;
}

void ecg_beats_reset(ecg_beats_t *b)
{
    b->clean_since = b->n_out;
    b->learned = false;
    biquad_design(&b->hp, 5.0f, BEATS_FS, true);
    biquad_design(&b->lp, 15.0f, BEATS_FS, false);
    memset(b->deriv_hist, 0, sizeof(b->deriv_hist));
    memset(b->sq_hist, 0, sizeof(b->sq_hist));
    b->mwi_sum = 0.0f;
    b->spki = b->npki = 0.0f;
    b->learn_max = b->learn_sum = 0.0f;
    b->learn_n = 0;
    b->last_qrs = NONE;
    b->last_qrs_slope = 0.0f;
    b->best_idx = NONE;
    b->best_val = 0.0f;
    b->wait_since = 0;
    b->rr_avg = 0.0f;
    b->rr_avg_n = 0;
    b->r_prev = NONE;
    b->n_pending = 0;
    b->rr_count = b->rr_next = 0;
}

void ecg_beats_init(ecg_beats_t *b, float counts_per_mv)
{
    memset(b, 0, sizeof(*b));
    b->counts_per_mv = counts_per_mv;
    /* Phase p holds the taps for an output that falls p/32 of an input sample after n0, for the
     * inputs n0 - HALF + 1 .. n0 + HALF. Blackman-windowed sinc, each phase normalised to unit
     * DC gain. */
    for (int p = 0; p < BEATS_RS_L; ++p) {
        const float frac = (float)p / BEATS_RS_L;
        float sum = 0.0f;
        for (int j = 0; j < 2 * BEATS_RS_HALF; ++j) {
            const float d = (float)(j - BEATS_RS_HALF + 1) - frac;
            const float arg = 2.0f * RS_CUTOFF * d;
            const float sinc = fabsf(arg) < 1e-6f ? 1.0f : sinf((float)M_PI * arg) / ((float)M_PI * arg);
            const float u = d / BEATS_RS_HALF;
            const float w = fabsf(u) >= 1.0f ? 0.0f
                          : 0.42f + 0.5f * cosf((float)M_PI * u) + 0.08f * cosf(2.0f * (float)M_PI * u);
            b->poly[p][j] = sinc * w;
            sum += b->poly[p][j];
        }
        for (int j = 0; j < 2 * BEATS_RS_HALF; ++j) b->poly[p][j] /= sum;
    }
    ecg_beats_reset(b);
}

static float rr_mean(const ecg_beats_t *b, size_t last)
{
    const size_t n = b->rr_count < last ? b->rr_count : last;
    float sum = 0.0f;
    for (size_t i = 1; i <= n; ++i) {
        sum += b->rr_hist[(b->rr_next + BEATS_RR_GLOBAL - i) % BEATS_RR_GLOBAL];
    }
    return n ? sum / (float)n : 0.0f;
}

/* Emits the oldest pending beat once the next R peak is known and its window is complete. */
static size_t emit_ready(ecg_beats_t *b, ecg_beat_t *out, size_t max)
{
    size_t n = 0;
    while (n < max && b->n_pending >= 2 && b->n_out > b->pending[0] + (BEATS_WIN - BEATS_WIN_BEFORE)) {
        const uint64_t r = b->pending[0];
        const float post = (float)(b->pending[1] - r);
        const float pre = b->r_prev == NONE ? post : (float)(r - b->r_prev);
        b->rr_hist[b->rr_next] = (uint16_t)(pre > 65535.0f ? 65535.0f : pre);
        b->rr_next = (b->rr_next + 1) % BEATS_RR_GLOBAL;
        if (b->rr_count < BEATS_RR_GLOBAL) ++b->rr_count;
        const float local = rr_mean(b, BEATS_RR_LOCAL), global = rr_mean(b, BEATS_RR_GLOBAL);
        b->r_prev = r;
        memmove(b->pending, b->pending + 1, (b->n_pending - 1) * sizeof(b->pending[0]));
        --b->n_pending;
        /* After a pause longer than the history, the window is gone: count the RR, skip the beat. */
        if (b->n_out - (r - BEATS_WIN_BEFORE) > BEATS_RING) continue;

        ecg_beat_t *beat = &out[n++];
        beat->r = r;
        for (int i = 0; i < BEATS_WIN; ++i) beat->win[i] = b->x[(r - BEATS_WIN_BEFORE + i) & MASK];
        beat->rr[0] = pre / local;
        beat->rr[1] = pre / global;
        beat->rr[2] = post / local;
        beat->rr[3] = post / global;
        beat->pre_rr_s = pre / BEATS_FS;
    }
    return n;
}

/* The R peak for a QRS whose MWI peak is at p: the largest deflection from the local mean. */
static void add_r_peak(ecg_beats_t *b, uint64_t p)
{
    uint64_t from = p >= R_SEARCH_FROM ? p - R_SEARCH_FROM : 0;
    if (from < b->clean_since) from = b->clean_since;
    const uint64_t to = p - R_SEARCH_TO;
    float mean = 0.0f;
    for (uint64_t i = from; i <= to; ++i) mean += b->x[i & MASK];
    mean /= (float)(to - from + 1);
    uint64_t r = from;
    float best = -1.0f;
    for (uint64_t i = from; i <= to; ++i) {
        const float d = fabsf(b->x[i & MASK] - mean);
        if (d > best) {
            best = d;
            r = i;
        }
    }
    if (b->n_pending && r <= b->pending[b->n_pending - 1]) return; /* same beat found twice */
    if (b->n_pending == BEATS_PENDING) { /* cannot happen at a sane rate; drop the oldest */
        memmove(b->pending, b->pending + 1, (BEATS_PENDING - 1) * sizeof(b->pending[0]));
        --b->n_pending;
    }
    b->pending[b->n_pending++] = r;
}

static void qrs_found(ecg_beats_t *b, uint64_t p, float pk, float slope, bool searchback)
{
    b->spki = searchback ? 0.25f * pk + 0.75f * b->spki : 0.125f * pk + 0.875f * b->spki;
    if (b->last_qrs != NONE) {
        const float rr = (float)(p - b->last_qrs);
        if (rr < STALE) {
            b->rr_avg = b->rr_avg_n ? 0.875f * b->rr_avg + 0.125f * rr : rr;
            ++b->rr_avg_n;
        }
    }
    b->last_qrs = p;
    b->wait_since = p;
    b->last_qrs_slope = slope;
    b->best_idx = NONE;
    b->best_val = 0.0f;
    add_r_peak(b, p);
}

/* One 128 Hz sample through the detector. k is its index; x and off are already stored. */
static void detect(ecg_beats_t *b, uint64_t k)
{
    const float bp = biquad(&b->lp, biquad(&b->hp, b->x[k & MASK]));
    float *h = b->deriv_hist; /* bp at k-1 .. k-4 */
    const float d = (2.0f * bp + h[0] - h[2] - 2.0f * h[3]) / 8.0f;
    h[3] = h[2];
    h[2] = h[1];
    h[1] = h[0];
    h[0] = bp;
    const float sq = d * d;
    b->slope[k & SLOPE_MASK] = sq;
    const size_t w = (size_t)(k % MWI_W);
    b->mwi_sum += sq - b->sq_hist[w];
    b->sq_hist[w] = sq;
    if (b->mwi_sum < 0.0f) b->mwi_sum = 0.0f;
    b->mwi[0] = b->mwi[1];
    b->mwi[1] = b->mwi[2];
    b->mwi[2] = b->mwi_sum / MWI_W;

    const uint64_t age = k - b->clean_since;
    if (age < SETTLE) return;
    if (!b->learned) {
        const float m = b->mwi[2];
        if (m > b->learn_max) b->learn_max = m;
        b->learn_sum += m;
        ++b->learn_n;
        if (age + 1 >= SETTLE + LEARN) {
            b->spki = 0.5f * b->learn_max;
            b->npki = 0.5f * b->learn_sum / (float)b->learn_n;
            b->learned = true;
            b->last_qrs = NONE;
            b->best_idx = NONE;
            b->best_val = 0.0f;
            b->last_qrs_slope = 0.0f;
            b->rr_avg_n = 0;
            b->npki = b->npki < b->spki ? b->npki : 0.0f;
            b->wait_since = k;
        }
        return;
    }

    const float thr1 = b->npki + 0.25f * (b->spki - b->npki);

    /* Is k-1 a local maximum of the MWI? */
    const uint64_t p = k - 1;
    if (p - 1 >= b->clean_since + SETTLE) {
        const float pk = b->mwi[1];
        if (pk > b->mwi[0] && pk >= b->mwi[2]) {
            float slope = 0.0f;
            for (uint64_t i = p - MWI_W + 1; i <= p; ++i) {
                if (b->slope[i & SLOPE_MASK] > slope) slope = b->slope[i & SLOPE_MASK];
            }
            const uint64_t gap = b->last_qrs == NONE ? UINT64_MAX : p - b->last_qrs;
            if (gap > REFRACTORY) {
                bool qrs = pk > thr1;
                if (qrs && gap < T_WAVE && slope < 0.5f * b->last_qrs_slope) qrs = false; /* T wave */
                if (qrs) {
                    qrs_found(b, p, pk, slope, false);
                } else {
                    b->npki = 0.125f * pk + 0.875f * b->npki;
                    if (pk > b->best_val && gap >= T_WAVE) {
                        b->best_val = pk;
                        b->best_idx = p;
                        b->best_slope = slope;
                    }
                }
            }
        }
    }

    /* Search-back: a long gap means a QRS under the threshold was missed. */
    if (b->last_qrs != NONE && b->rr_avg_n >= 2 && b->best_idx != NONE &&
        (float)(k - b->last_qrs) > 1.66f * b->rr_avg && b->best_val > 0.5f * thr1) {
        qrs_found(b, b->best_idx, b->best_val, b->best_slope, true);
    } else if (k - b->wait_since > STALE) {
        /* Nothing for 3 s: the thresholds are too high (after an artefact, say). The RR average
         * restarts, so the next interval is not compared with the old rhythm. */
        b->spki *= 0.5f;
        b->npki *= 0.5f;
        b->wait_since = k;
        b->rr_avg_n = 0;
    }
}

size_t ecg_beats_push(ecg_beats_t *b, const int16_t *counts, const uint8_t *off, size_t n,
                      ecg_beat_t *out, size_t max)
{
    size_t emitted = 0;
    for (size_t i = 0; i < n; ++i) {
        b->in[b->n_in & IN_MASK] = (float)counts[i] / b->counts_per_mv;
        b->in_off[b->n_in & IN_MASK] = off ? off[i] : 0;
        ++b->n_in;

        /* Produce every 128 Hz output whose taps are all in. */
        for (;;) {
            const uint64_t pos = b->n_out * BEATS_RS_M;
            const uint64_t n0 = pos / BEATS_RS_L;
            if (n0 + BEATS_RS_HALF >= b->n_in) break;
            const float *taps = b->poly[pos % BEATS_RS_L];
            float y = 0.0f;
            uint8_t lo = 0;
            for (int j = 0; j < 2 * BEATS_RS_HALF; ++j) {
                const int64_t idx = (int64_t)n0 - BEATS_RS_HALF + 1 + j;
                const uint64_t at = idx < 0 ? 0 : (uint64_t)idx;
                y += taps[j] * b->in[at & IN_MASK];
                lo |= b->in_off[at & IN_MASK];
            }
            const uint64_t k = b->n_out++;
            b->x[k & MASK] = lo ? 0.0f : y;
            if (lo) {
                ecg_beats_reset(b); /* clean_since becomes the next sample */
                continue;
            }
            detect(b, k);
            emitted += emit_ready(b, out + emitted, max - emitted);
        }
    }
    return emitted;
}
