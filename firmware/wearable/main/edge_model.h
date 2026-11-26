#pragma once

/* The on-device model: a task reads the sampler's ring, finds beats (ecg_beats.c), classifies
 * each with the 1D-CNN (ecg_model/) and applies the alert rule (edge_rule.c). */

#include <stdbool.h>
#include <stdint.h>

#include "edge_rule.h"
#include "esp_err.h"

/* What the OLED's ECG page shows. */
typedef struct {
    float bpm;        /* mean of the last 8 RR intervals */
    char last;        /* the last beat's class: 'N', 'S' or 'V' */
    uint32_t beats[3]; /* N, S and V beats since boot */
    uint32_t infer_us_avg; /* model time per beat: running average */
    uint32_t infer_us_max; /* and the slowest since boot */
} edge_status_t;

/* Called on the model task when the rule raises an alert; must not block. */
typedef void (*edge_alert_handler_t)(const edge_alert_t *alert);

#if CONFIG_WEARABLE_EDGE_MODEL
/* Starts the task after ecg_sampler_start. Fails without stopping the rest of the firmware. */
esp_err_t edge_model_start(void);
void edge_model_set_alert_handler(edge_alert_handler_t handler);
/* Fills *out; returns false while no beat has been classified in the last 3 s. */
bool edge_model_status(edge_status_t *out);
#else
static inline esp_err_t edge_model_start(void) { return ESP_OK; }
static inline void edge_model_set_alert_handler(edge_alert_handler_t handler) { (void)handler; }
static inline bool edge_model_status(edge_status_t *out) { *out = (edge_status_t){0}; return false; }
#endif
