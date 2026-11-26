#pragma once

/* The on-device alert rule, with no ESP-IDF dependency so the host test (TC-W09) can build it:
 * an alert when at least min_abnormal of the last window classified beats are S or V, and at
 * least cooldown_ms after the previous alert. The alert's label is the more frequent of S and V
 * in the window (V on a tie), its confidence the mean probability of that class over those beats. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define EDGE_RULE_MAX_WINDOW 32

typedef struct {
    size_t window, min_abnormal;
    int64_t cooldown_ms;
    uint8_t cls[EDGE_RULE_MAX_WINDOW];
    float prob[EDGE_RULE_MAX_WINDOW]; /* the probability of the predicted class */
    size_t n, next;
    bool alerted;
    int64_t last_alert_ms;
} edge_rule_t;

typedef struct {
    const char *label; /* "S" or "V", as the dashboard's beat classes */
    float confidence;
    size_t abnormal;   /* S and V beats in the window */
} edge_alert_t;

void edge_rule_init(edge_rule_t *r, size_t window, size_t min_abnormal, int64_t cooldown_ms);

/* Adds one classified beat (0 = N, 1 = S, 2 = V) with its class probabilities. Returns true and
 * fills *out when the beat completes an alert. */
bool edge_rule_push(edge_rule_t *r, int cls, const float probs[3], int64_t now_ms, edge_alert_t *out);

/* Forgets the window (leads off, lost samples); the cooldown is kept. */
void edge_rule_clear(edge_rule_t *r);
