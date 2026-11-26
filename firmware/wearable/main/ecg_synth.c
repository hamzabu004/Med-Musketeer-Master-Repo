/* SYNTH front end: a generated 72 bpm trace at 500 SPS, paced by esp_timer, for bench runs without
 * electrodes. The beat shape is alert.c's; it is a recognisable trace, not a clinical signal.
 * Leads are always on. */
#include <math.h>

#include "ecg_frontend.h"
#include "esp_timer.h"
#include "freertos/task.h"

#define SYNTH_FS_HZ 500
#define SYNTH_COUNTS_PER_MV 200
#define BEAT_S (60.0f / 72.0f)

static const struct {
    float mv, centre_s, width_s;
} waves[] = {
    {0.15f, 0.20f, 0.025f},  /* P */
    {-0.10f, 0.33f, 0.010f}, /* Q */
    {1.20f, 0.36f, 0.012f},  /* R */
    {-0.25f, 0.39f, 0.012f}, /* S */
    {0.30f, 0.60f, 0.040f},  /* T */
};

static int64_t start_us;
static uint64_t produced;

static int16_t synth_sample(uint64_t index)
{
    const float t = fmodf((float)(index % (SYNTH_FS_HZ * 60)) / SYNTH_FS_HZ, BEAT_S);
    float mv = 0.0f;
    for (size_t w = 0; w < sizeof(waves) / sizeof(waves[0]); ++w) {
        const float d = (t - waves[w].centre_s) / waves[w].width_s;
        mv += waves[w].mv * expf(-0.5f * d * d);
    }
    return (int16_t)lrintf(mv * SYNTH_COUNTS_PER_MV);
}

static esp_err_t synth_init(void) { return ESP_OK; }

static esp_err_t synth_start(void)
{
    start_us = esp_timer_get_time();
    produced = 0;
    return ESP_OK;
}

static esp_err_t synth_stop(void) { return ESP_OK; }

static size_t synth_read(int16_t *out, uint8_t *leads_off, size_t max, TickType_t timeout)
{
    const TickType_t begin = xTaskGetTickCount();
    for (;;) {
        const uint64_t due = (uint64_t)(esp_timer_get_time() - start_us) * SYNTH_FS_HZ / 1000000;
        if (due > produced) {
            size_t n = due - produced < max ? (size_t)(due - produced) : max;
            for (size_t i = 0; i < n; ++i) {
                out[i] = synth_sample(produced + i);
                leads_off[i] = 0;
            }
            produced += n;
            return n;
        }
        const TickType_t waited = xTaskGetTickCount() - begin;
        if (waited >= timeout) return 0;
        const TickType_t step = pdMS_TO_TICKS(20) ? pdMS_TO_TICKS(20) : 1;
        vTaskDelay(timeout - waited < step ? timeout - waited : step);
    }
}

const ecg_frontend_t ecg_frontend_synth = {
    .sensor = "SYNTH",
    .lead = CONFIG_WEARABLE_ECG_LEAD,
    .fs_hz = SYNTH_FS_HZ,
    .counts_per_mv = SYNTH_COUNTS_PER_MV,
    .init = synth_init,
    .start = synth_start,
    .stop = synth_stop,
    .read = synth_read,
    .take_lost = NULL,
};
