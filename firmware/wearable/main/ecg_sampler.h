#pragma once

/* The always-on ECG sampler (Iteration 5, D-3): a task reads the front end from boot into a 12 s
 * ring of samples and leads-off flags. Sample i was taken at ecg_sampler_time_us(i); there are no
 * per-chunk timestamps. The on-demand stream (Slice 3) copies chunks out of the ring. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "ecg_frontend.h"
#include "esp_err.h"

#define ECG_RING_SECONDS 12 /* a 10 s alert segment plus room to copy it while sampling goes on */

typedef enum {
    ECG_STATE_OFF,       /* not started */
    ECG_STATE_ERROR,     /* the front end failed to start, or no samples for over a second */
    ECG_STATE_LEADS_OFF, /* a lead was off within the last second */
    ECG_STATE_READY,
} ecg_state_t;

/* Initialises and starts the front end chosen in Kconfig and the sampler task. On failure the
 * state stays ECG_STATE_ERROR and the rest of the firmware runs without ECG. */
esp_err_t ecg_sampler_start(void);

const ecg_frontend_t *ecg_sampler_frontend(void);
ecg_state_t ecg_sampler_state(void);

/* Index of the next sample to be written; samples [head - ring size, head) can be copied. */
uint64_t ecg_sampler_head(void);

/* Copies up to n samples starting at index first; leads_off may be NULL. Returns how many were
 * copied: fewer when the ring does not yet hold them, 0 when first has already been overwritten. */
size_t ecg_sampler_copy(uint64_t first, size_t n, int16_t *out, uint8_t *leads_off);

/* Wall-clock time of sample index in microseconds since the epoch, or false while the clock is
 * not yet valid (before SNTP). The anchor is refreshed once a minute, so it follows SNTP. */
bool ecg_sampler_time_us(uint64_t index, int64_t *out);
