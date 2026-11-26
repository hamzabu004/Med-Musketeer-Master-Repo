#pragma once

/* An ECG front end: the ADS1292, or SYNTH for bench runs without electrodes. The sampler (ecg_sampler.c) and the stream use only this interface, so changing the
 * front end changes neither the stream nor the contracts. Chosen by Kconfig WEARABLE_ECG_FRONTEND. */

#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

typedef struct {
    const char *sensor;     /* "ADS1292", "SYNTH" */
    const char *lead;       /* Kconfig WEARABLE_ECG_LEAD */
    uint16_t fs_hz;         /* output samples per second */
    uint16_t counts_per_mv; /* int16 counts per mV at the electrodes */
    esp_err_t (*init)(void);
    esp_err_t (*start)(void);
    esp_err_t (*stop)(void);
    /* Blocks up to timeout for samples; fills out[] and one leads-off flag (0 or 1) per sample,
     * at most max of each. Returns how many were written; 0 means none arrived in time. */
    size_t (*read)(int16_t *out, uint8_t *leads_off, size_t max, TickType_t timeout);
    /* Samples lost since the last call (the front end could not keep up); NULL if it cannot
     * lose any. */
    uint32_t (*take_lost)(void);
} ecg_frontend_t;

extern const ecg_frontend_t ecg_frontend_ads1292;
extern const ecg_frontend_t ecg_frontend_synth;

/* The front end chosen in Kconfig. */
const ecg_frontend_t *ecg_frontend(void);
