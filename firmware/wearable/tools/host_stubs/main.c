/* Host build of main/alert.c for test_check_capture.py: prints three alerts as mosquitto_sub -v
 * lines: two button alerts with the synthetic fallback trace, then a model alert carrying a 10 s
 * segment at 500 SPS as the wearable sends it. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>

#include "alert.h"
#include "cJSON.h"

int main(int argc, char **argv)
{
    const char *device_id = argc > 1 ? argv[1] : "00000000-0000-4000-8000-000000000000";
    uint64_t seq = 0;
    for (; seq < 2; ++seq) {
        char *payload = alert_build(seq, NULL);
        if (!payload) return 1;
        printf("mm/fixed/%s/alert %s\n", device_id, payload);
        cJSON_free(payload);
    }

    static int16_t samples[ALERT_SEGMENT_S * 500];
    const size_t n = sizeof(samples) / sizeof(samples[0]);
    for (size_t i = 0; i < n; ++i) { /* a full-scale-ish pattern, so every byte value occurs */
        samples[i] = (int16_t)lrint(30000.0 * sin((double)i * 0.37));
    }
    struct timeval now;
    gettimeofday(&now, NULL);
    const alert_segment_t seg = {
        .samples = samples,
        .n_samples = n,
        .fs_hz = 500,
        .lead = "II",
        .start_us = (int64_t)now.tv_sec * 1000000 + now.tv_usec - 10 * 1000000LL,
        .label = "V",
        .confidence = 0.875,
        .model = "farag-1dcnn-p1best-int8-s0",
    };
    char *payload = alert_build(seq, &seg);
    if (!payload) return 1;
    printf("mm/fixed/%s/alert %s\n", device_id, payload);
    cJSON_free(payload);
    return 0;
}
