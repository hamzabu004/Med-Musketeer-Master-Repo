#pragma once

#include <stdint.h>

#define ALERT_FS_HZ 360
#define ALERT_N_SAMPLES 1080 /* 3 s */

/* Builds one alert-payload-v1 (shared/contracts/alert-payload-v1.schema.json) carrying a synthetic
 * ECG segment that ends now. There is no on-device model yet (Iteration 5), so `screening` is a
 * fixed stub. Returns a string to release with cJSON_free, or NULL. */
char *alert_build(uint64_t seq);
