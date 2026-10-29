#include "alert.h"

#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <sys/time.h>
#include <time.h>

#include "cJSON.h"
#include "esp_random.h"
#include "mbedtls/base64.h"

#define COUNTS_PER_MV 200.0f /* MIT-BIH's gain, which the cloud and dashboard assume */
#define BEAT_S (60.0f / 72.0f)
#define SAMPLE_BYTES (ALERT_N_SAMPLES * 2)
#define BASE64_LEN (((SAMPLE_BYTES + 2) / 3) * 4)

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

static uint8_t sample_bytes[SAMPLE_BYTES];
static char samples_base64[BASE64_LEN + 1];
static bool samples_ready;

static bool prepare_samples(void)
{
    for (int i = 0; i < ALERT_N_SAMPLES; ++i) {
        float t = fmodf((float)i / ALERT_FS_HZ, BEAT_S);
        float mv = 0.0f;
        for (size_t w = 0; w < sizeof(waves) / sizeof(waves[0]); ++w) {
            float d = (t - waves[w].centre_s) / waves[w].width_s;
            mv += waves[w].mv * expf(-0.5f * d * d);
        }
        int16_t counts = (int16_t)lrintf(mv * COUNTS_PER_MV);
        sample_bytes[2 * i] = (uint8_t)(counts & 0xff); /* little-endian */
        sample_bytes[2 * i + 1] = (uint8_t)((uint16_t)counts >> 8);
    }
    size_t written = 0;
    if (mbedtls_base64_encode((unsigned char *)samples_base64, sizeof(samples_base64), &written,
                              sample_bytes, sizeof(sample_bytes)) != 0) {
        return false;
    }
    samples_ready = true;
    return true;
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

static void rfc3339(const struct timeval *tv, char out[32])
{
    struct tm utc;
    gmtime_r(&tv->tv_sec, &utc);
    size_t n = strftime(out, 32, "%Y-%m-%dT%H:%M:%S", &utc);
    snprintf(out + n, 32 - n, ".%03dZ", (int)(tv->tv_usec / 1000));
}

char *alert_build(uint64_t seq)
{
    if (!samples_ready && !prepare_samples()) return NULL;

    struct timeval now;
    gettimeofday(&now, NULL);
    /* The segment is the last 3 s before the press. */
    int64_t start_us = (int64_t)now.tv_sec * 1000000 + now.tv_usec
                       - (int64_t)ALERT_N_SAMPLES * 1000000 / ALERT_FS_HZ;
    struct timeval start = {.tv_sec = start_us / 1000000, .tv_usec = start_us % 1000000};

    char msg_id[37], segment_start[32], sent_at[32];
    uuid4(msg_id);
    rfc3339(&start, segment_start);
    rfc3339(&now, sent_at);

    cJSON *alert = cJSON_CreateObject();
    cJSON *screening = cJSON_CreateObject();
    bool ok = alert && screening &&
              cJSON_AddStringToObject(screening, "label", "abnormal") &&
              cJSON_AddNumberToObject(screening, "confidence", 1.0) &&
              cJSON_AddStringToObject(screening, "model", "button-stub-0") &&
              cJSON_AddNumberToObject(alert, "v", 1) &&
              cJSON_AddStringToObject(alert, "msg_id", msg_id) &&
              cJSON_AddNumberToObject(alert, "seq", (double)seq) &&
              cJSON_AddStringToObject(alert, "type", "alert") &&
              cJSON_AddNumberToObject(alert, "fs_hz", ALERT_FS_HZ) &&
              cJSON_AddStringToObject(alert, "lead", "SYNTH") &&
              cJSON_AddNumberToObject(alert, "n_samples", ALERT_N_SAMPLES) &&
              cJSON_AddStringToObject(alert, "encoding", "int16le-base64") &&
              cJSON_AddStringToObject(alert, "samples", samples_base64) &&
              cJSON_AddItemToObject(alert, "screening", screening);
    if (ok) screening = NULL; /* now owned by alert */
    ok = ok &&
         cJSON_AddStringToObject(alert, "segment_start", segment_start) &&
         cJSON_AddStringToObject(alert, "sent_at", sent_at);

    char *payload = ok ? cJSON_PrintUnformatted(alert) : NULL;
    cJSON_Delete(screening);
    cJSON_Delete(alert);
    return payload;
}
