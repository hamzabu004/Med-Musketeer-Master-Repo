#include "alert.h"

#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>
#include <time.h>

#include "cJSON.h"
#include "esp_random.h"
#include "mbedtls/base64.h"

#define COUNTS_PER_MV 200.0f /* MIT-BIH's gain, which the cloud and dashboard assume */
#define BEAT_S (60.0f / 72.0f)

/* One beat as a sum of Gaussian waves: amplitude in mV, centre and width in seconds from the
 * start of the beat. Only a recognisable trace for the dashboard, not a clinical signal. */
static const struct {
    float mv, centre_s, width_s;
} waves[] = {
    {0.15f, 0.20f, 0.025f},  /* P */
    {-0.10f, 0.33f, 0.010f}, /* Q */
    {1.20f, 0.36f, 0.012f},  /* R */
    {-0.25f, 0.39f, 0.012f}, /* S */
    {0.30f, 0.60f, 0.040f},  /* T */
};

static int16_t synthetic[ALERT_N_SAMPLES];
static bool synthetic_ready;

static void prepare_synthetic(void)
{
    for (int i = 0; i < ALERT_N_SAMPLES; ++i) {
        float t = fmodf((float)i / ALERT_FS_HZ, BEAT_S);
        float mv = 0.0f;
        for (size_t w = 0; w < sizeof(waves) / sizeof(waves[0]); ++w) {
            float d = (t - waves[w].centre_s) / waves[w].width_s;
            mv += waves[w].mv * expf(-0.5f * d * d);
        }
        synthetic[i] = (int16_t)lrintf(mv * COUNTS_PER_MV);
    }
    synthetic_ready = true;
}

/* The samples as little-endian int16, Base64 with padding; malloc'd, or NULL. */
static char *encode_samples(const int16_t *samples, size_t n)
{
    uint8_t *bytes = malloc(2 * n);
    const size_t len = (2 * n + 2) / 3 * 4 + 1;
    char *out = malloc(len);
    size_t written = 0;
    if (bytes && out) {
        for (size_t i = 0; i < n; ++i) {
            bytes[2 * i] = (uint8_t)((uint16_t)samples[i] & 0xff);
            bytes[2 * i + 1] = (uint8_t)((uint16_t)samples[i] >> 8);
        }
        if (mbedtls_base64_encode((unsigned char *)out, len, &written, bytes, 2 * n) != 0) {
            free(out);
            out = NULL;
        }
    } else {
        free(out);
        out = NULL;
    }
    free(bytes);
    return out;
}

static void uuid4(char out[37])
{
    uint8_t b[16];
    esp_fill_random(b, sizeof(b));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    snprintf(out, 37, "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
             b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7],
             b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]);
}

static void rfc3339(int64_t us, char out[32])
{
    const time_t sec = (time_t)(us / 1000000);
    struct tm utc;
    gmtime_r(&sec, &utc);
    size_t n = strftime(out, 32, "%Y-%m-%dT%H:%M:%S", &utc);
    snprintf(out + n, 32 - n, ".%03dZ", (int)(us % 1000000 / 1000));
}

char *alert_build(uint64_t seq, const alert_segment_t *segment)
{
    struct timeval now;
    gettimeofday(&now, NULL);
    const int64_t now_us = (int64_t)now.tv_sec * 1000000 + now.tv_usec;

    alert_segment_t fallback;
    if (!segment) {
        if (!synthetic_ready) prepare_synthetic();
        fallback = (alert_segment_t){
            .samples = synthetic,
            .n_samples = ALERT_N_SAMPLES,
            .fs_hz = ALERT_FS_HZ,
            .lead = "SYNTH",
            /* The segment is the last 3 s before the press. */
            .start_us = now_us - (int64_t)ALERT_N_SAMPLES * 1000000 / ALERT_FS_HZ,
            .label = "abnormal",
            .confidence = 1.0,
            .model = "button-stub-0",
        };
        segment = &fallback;
    }

    char *samples_base64 = encode_samples(segment->samples, segment->n_samples);
    if (!samples_base64) return NULL;

    char msg_id[37], segment_start[32], sent_at[32];
    uuid4(msg_id);
    rfc3339(segment->start_us, segment_start);
    rfc3339(now_us, sent_at);

    cJSON *alert = cJSON_CreateObject();
    cJSON *screening = cJSON_CreateObject();
    cJSON *samples = cJSON_CreateStringReference(samples_base64); /* not copied */
    bool ok = alert && screening && samples &&
              cJSON_AddStringToObject(screening, "label", segment->label) &&
              cJSON_AddNumberToObject(screening, "confidence", segment->confidence) &&
              cJSON_AddStringToObject(screening, "model", segment->model) &&
              cJSON_AddNumberToObject(alert, "v", 1) &&
              cJSON_AddStringToObject(alert, "msg_id", msg_id) &&
              cJSON_AddNumberToObject(alert, "seq", (double)seq) &&
              cJSON_AddStringToObject(alert, "type", "alert") &&
              cJSON_AddNumberToObject(alert, "fs_hz", segment->fs_hz) &&
              cJSON_AddStringToObject(alert, "lead", segment->lead) &&
              cJSON_AddNumberToObject(alert, "n_samples", (double)segment->n_samples) &&
              cJSON_AddStringToObject(alert, "encoding", "int16le-base64") &&
              cJSON_AddItemToObject(alert, "samples", samples);
    if (ok) samples = NULL; /* now owned by alert */
    ok = ok && cJSON_AddItemToObject(alert, "screening", screening);
    if (ok) screening = NULL;
    ok = ok &&
         cJSON_AddStringToObject(alert, "segment_start", segment_start) &&
         cJSON_AddStringToObject(alert, "sent_at", sent_at);

    char *payload = ok ? cJSON_PrintUnformatted(alert) : NULL;
    cJSON_Delete(samples);
    cJSON_Delete(screening);
    cJSON_Delete(alert);
    free(samples_base64);
    return payload;
}
