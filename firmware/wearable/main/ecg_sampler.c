#include "ecg_sampler.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>
#include <time.h>

#include "elog.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#define READ_MAX 64                  /* samples per front-end read */
#define READ_TIMEOUT_MS 200
#define STALL_MS 1000                /* no samples for this long: ECG_STATE_ERROR */
#define ANCHOR_EVERY_US (60 * 1000000LL)
#define RATE_LOG_EVERY_US (60 * 1000000LL)
#define CLOCK_VALID_AFTER 1704067200 /* as fixed_path.c: 2024-01-01, so SNTP has set the clock */
#define DUMP_EVERY_US (5 * 1000000LL)
#define SAMPLER_PRIORITY 6           /* above the network (5) and alert (4) tasks */

static const char *TAG = "ecg_sampler";

const ecg_frontend_t *ecg_frontend(void)
{
#if CONFIG_WEARABLE_ECG_FRONTEND_ADS1292
    return &ecg_frontend_ads1292;
#else
    return &ecg_frontend_synth;
#endif
}

static const ecg_frontend_t *fe;
static int16_t *ring;
static uint8_t *ring_off;
static size_t ring_len;
static SemaphoreHandle_t lock;
static uint64_t head;                 /* guarded by lock */
static uint64_t last_leads_off = UINT64_MAX; /* index of the newest leads-off sample; guarded */
static int64_t t0_us;                 /* wall-clock time of sample 0; 0 = not anchored; guarded */
static volatile int64_t last_sample_at_us;
static volatile bool started;
static volatile bool failed;

static void anchor_clock(uint64_t newest_index)
{
    struct timeval now;
    gettimeofday(&now, NULL);
    if (now.tv_sec < CLOCK_VALID_AFTER) return;
    /* The newest sample was taken within one ADC frame (32 ms) of now. */
    const int64_t now_us = (int64_t)now.tv_sec * 1000000 + now.tv_usec;
    const int64_t t0 = now_us - (int64_t)(newest_index * 1000000 / fe->fs_hz);
    xSemaphoreTake(lock, portMAX_DELAY);
    t0_us = t0;
    xSemaphoreGive(lock);
}

#if CONFIG_WEARABLE_ECG_DEBUG_DUMP
/* Prints the last second of samples on one line: "ECG_DUMP fs=500 lo=<count>: v v v ...". */
static void dump_last_second(void)
{
    static int16_t samples[1000];
    static uint8_t flags[1000];
    const size_t want = fe->fs_hz < 1000 ? fe->fs_hz : 1000;
    const uint64_t h = ecg_sampler_head();
    if (h < want) return;
    const size_t n = ecg_sampler_copy(h - want, want, samples, flags);
    size_t lo = 0;
    for (size_t i = 0; i < n; ++i) lo += flags[i] != 0;
    printf("ECG_DUMP fs=%u lo=%u:", fe->fs_hz, (unsigned)lo);
    for (size_t i = 0; i < n; ++i) printf(" %d", samples[i]);
    printf("\n");
}
#endif

static void sampler_task(void *arg)
{
    (void)arg;
    static int16_t buf[READ_MAX];
    static uint8_t off[READ_MAX];
    int64_t anchored_at = 0, rate_since = esp_timer_get_time();
    uint64_t rate_samples = 0, rate_leads_off = 0;
    for (;;) {
        const size_t n = fe->read(buf, off, READ_MAX, pdMS_TO_TICKS(READ_TIMEOUT_MS));
        const int64_t now = esp_timer_get_time();
        if (!n) continue;
        last_sample_at_us = now;

        xSemaphoreTake(lock, portMAX_DELAY);
        for (size_t i = 0; i < n; ++i) {
            const size_t slot = (size_t)(head % ring_len);
            ring[slot] = buf[i];
            ring_off[slot] = off[i];
            if (off[i]) last_leads_off = head;
            ++head;
        }
        const uint64_t newest = head - 1;
        const bool anchored = t0_us != 0;
        const bool leads_off_now = last_leads_off != UINT64_MAX && head - last_leads_off <= fe->fs_hz;
        xSemaphoreGive(lock);

        static bool leads_off_logged;
        if (leads_off_now != leads_off_logged) {
            elog_add(leads_off_now ? "LEADS OFF" : "LEADS ON");
            leads_off_logged = leads_off_now;
        }

        if (!anchored || now - anchored_at >= ANCHOR_EVERY_US) {
            anchor_clock(newest);
            anchored_at = now;
        }

#if CONFIG_WEARABLE_ECG_DEBUG_DUMP
        static int64_t dumped_at;
        if (now - dumped_at >= DUMP_EVERY_US) {
            dump_last_second();
            dumped_at = now;
        }
#endif
        rate_samples += n;
        for (size_t i = 0; i < n; ++i) rate_leads_off += off[i] != 0;
        if (now - rate_since >= RATE_LOG_EVERY_US) {
            const double secs = (now - rate_since) / 1e6;
            const uint32_t lost = fe->take_lost ? fe->take_lost() : 0;
            ESP_LOGI(TAG, "%s: %" PRIu64 " samples in %.3f s = %.2f SPS; %" PRIu64 " with leads off; %" PRIu32 " lost",
                     fe->sensor, rate_samples, secs, rate_samples / secs, rate_leads_off, lost);
            rate_since = now;
            rate_samples = rate_leads_off = 0;
        }
    }
}

esp_err_t ecg_sampler_start(void)
{
    fe = ecg_frontend();
    failed = true;
    ring_len = (size_t)fe->fs_hz * ECG_RING_SECONDS;
    ring = calloc(ring_len, sizeof(*ring));
    ring_off = calloc(ring_len, sizeof(*ring_off));
    lock = xSemaphoreCreateMutex();
    if (!ring || !ring_off || !lock) {
        ESP_LOGE(TAG, "No memory for the ECG ring");
        return ESP_ERR_NO_MEM;
    }
    esp_err_t err = fe->init();
    if (err == ESP_OK) err = fe->start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "%s front end did not start: %s", fe->sensor, esp_err_to_name(err));
        elog_add("ECG ERROR");
        return err;
    }
    last_sample_at_us = esp_timer_get_time();
    if (xTaskCreatePinnedToCore(sampler_task, "ecg_sampler", 4096, NULL, SAMPLER_PRIORITY, NULL, 1) != pdPASS) {
        fe->stop();
        ESP_LOGE(TAG, "Cannot start the sampler task");
        return ESP_ERR_NO_MEM;
    }
    failed = false;
    started = true;
    ESP_LOGI(TAG, "%s at %u SPS, lead %s, %u counts/mV; %u s ring", fe->sensor, fe->fs_hz,
             fe->lead, fe->counts_per_mv, ECG_RING_SECONDS);
    return ESP_OK;
}

const ecg_frontend_t *ecg_sampler_frontend(void)
{
    return fe;
}

ecg_state_t ecg_sampler_state(void)
{
    if (failed) return ECG_STATE_ERROR;
    if (!started) return ECG_STATE_OFF;
    if (esp_timer_get_time() - last_sample_at_us > STALL_MS * 1000LL) return ECG_STATE_ERROR;
    xSemaphoreTake(lock, portMAX_DELAY);
    const bool recent = last_leads_off != UINT64_MAX && head - last_leads_off <= fe->fs_hz;
    xSemaphoreGive(lock);
    return recent ? ECG_STATE_LEADS_OFF : ECG_STATE_READY;
}

uint64_t ecg_sampler_head(void)
{
    if (!started) return 0;
    xSemaphoreTake(lock, portMAX_DELAY);
    const uint64_t h = head;
    xSemaphoreGive(lock);
    return h;
}

size_t ecg_sampler_copy(uint64_t first, size_t n, int16_t *out, uint8_t *leads_off)
{
    if (!started) return 0;
    xSemaphoreTake(lock, portMAX_DELAY);
    size_t copied = 0;
    const uint64_t oldest = head > ring_len ? head - ring_len : 0;
    if (first >= oldest && first < head) {
        copied = head - first < n ? (size_t)(head - first) : n;
        for (size_t i = 0; i < copied; ++i) {
            const size_t slot = (size_t)((first + i) % ring_len);
            out[i] = ring[slot];
            if (leads_off) leads_off[i] = ring_off[slot];
        }
    }
    xSemaphoreGive(lock);
    return copied;
}

bool ecg_sampler_time_us(uint64_t index, int64_t *out)
{
    if (!started) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    const int64_t t0 = t0_us;
    xSemaphoreGive(lock);
    if (!t0) return false;
    *out = t0 + (int64_t)(index * 1000000 / fe->fs_hz);
    return true;
}
