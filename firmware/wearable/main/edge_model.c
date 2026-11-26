#include "edge_model.h"

#include <inttypes.h>

#include "ecg_beats.h"
#include "ecg_convert.h"
#include "ecg_classifier.h"
#include "ecg_sampler.h"
#include "elog.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define POLL_MS 100
#define CHUNK 256
#define MAX_BEATS 8
#define STATS_EVERY_US (60 * 1000000LL)
#define EDGE_PRIORITY 3 /* under the sampler (6), the network (5) and the alert task (4) */

static const char *TAG = "edge_model";
#define STATUS_RR 8
#define STATUS_STALE_US (3 * 1000000LL)

static volatile edge_alert_handler_t alert_handler;
static portMUX_TYPE status_lock = portMUX_INITIALIZER_UNLOCKED;
static float status_rr[STATUS_RR];
static size_t status_rr_n, status_rr_next;
static char status_last;
static uint32_t status_beats[3];
static int64_t status_at_us;
static float status_infer_avg;
static uint32_t status_infer_max;

static void note_beat(int cls, float rr_s, int64_t infer_us)
{
    taskENTER_CRITICAL(&status_lock);
    status_infer_avg = status_infer_avg > 0.0f ? 0.95f * status_infer_avg + 0.05f * (float)infer_us
                                               : (float)infer_us;
    if (infer_us > status_infer_max) status_infer_max = (uint32_t)infer_us;
    status_rr[status_rr_next] = rr_s;
    status_rr_next = (status_rr_next + 1) % STATUS_RR;
    if (status_rr_n < STATUS_RR) ++status_rr_n;
    status_last = "NSV"[cls];
    ++status_beats[cls];
    status_at_us = esp_timer_get_time();
    taskEXIT_CRITICAL(&status_lock);
}

bool edge_model_status(edge_status_t *out)
{
    taskENTER_CRITICAL(&status_lock);
    const bool fresh = status_at_us && esp_timer_get_time() - status_at_us < STATUS_STALE_US;
    float sum = 0.0f;
    for (size_t i = 0; i < status_rr_n; ++i) sum += status_rr[i];
    out->bpm = sum > 0.0f ? 60.0f * (float)status_rr_n / sum : 0.0f;
    out->last = status_last;
    for (int i = 0; i < 3; ++i) out->beats[i] = status_beats[i];
    out->infer_us_avg = (uint32_t)(status_infer_avg + 0.5f);
    out->infer_us_max = status_infer_max;
    taskEXIT_CRITICAL(&status_lock);
    return fresh;
}

void edge_model_set_alert_handler(edge_alert_handler_t handler)
{
    alert_handler = handler;
}

static void edge_task(void *arg)
{
    (void)arg;
    static ecg_beats_t beats;
    static ecg_beat_t found[MAX_BEATS];
    static int16_t buf[CHUNK];
    static uint8_t off[CHUNK];
    static edge_rule_t rule;

    const ecg_frontend_t *fe = ecg_sampler_frontend();
    ecg_beats_init(&beats, fe->counts_per_mv);
    edge_rule_init(&rule, CONFIG_WEARABLE_EDGE_ALERT_WINDOW_BEATS,
                   CONFIG_WEARABLE_EDGE_ALERT_MIN_ABNORMAL,
                   (int64_t)CONFIG_WEARABLE_EDGE_ALERT_COOLDOWN_S * 1000);
    uint64_t next = ecg_sampler_head();
    uint32_t count[3] = {0, 0, 0}, failed = 0, behind = 0;
    float rr_sum = 0.0f;
    int64_t stats_since = esp_timer_get_time(), worst_us = 0;

    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(POLL_MS));
        const uint64_t head = ecg_sampler_head();
        while (next < head) {
            const size_t want = head - next < CHUNK ? (size_t)(head - next) : CHUNK;
            const size_t got = ecg_sampler_copy(next, want, buf, off);
            if (!got) { /* the ring overwrote what was not yet read */
                ++behind;
                next = head;
                ecg_beats_reset(&beats);
                edge_rule_clear(&rule);
                break;
            }
            next += got;
            if (ecg_count_leads_off(off, got)) edge_rule_clear(&rule);
            const size_t n = ecg_beats_push(&beats, buf, off, got, found, MAX_BEATS);
            for (size_t i = 0; i < n; ++i) {
                float probs[3];
                const int64_t t0 = esp_timer_get_time();
                const int cls = ecg_classify_beat(found[i].win, found[i].rr, probs);
                const int64_t took = esp_timer_get_time() - t0;
                if (took > worst_us) worst_us = took;
                if (cls < 0) {
                    ++failed;
                    continue;
                }
                ++count[cls];
                rr_sum += found[i].pre_rr_s;
                note_beat(cls, found[i].pre_rr_s, took);
                ESP_LOGD(TAG, "beat %c  P(N,S,V) %.2f %.2f %.2f  RR %.3f s", "NSV"[cls], probs[0],
                         probs[1], probs[2], found[i].pre_rr_s);
                edge_alert_t alert;
                if (edge_rule_push(&rule, cls, probs, esp_timer_get_time() / 1000, &alert)) {
                    ESP_LOGW(TAG, "Alert: %u of the last %u beats abnormal, label %s, confidence %.2f",
                             (unsigned)alert.abnormal, (unsigned)rule.n, alert.label, alert.confidence);
                    const edge_alert_handler_t handler = alert_handler;
                    if (handler) handler(&alert);
                }
            }
        }

        const int64_t now = esp_timer_get_time();
        if (now - stats_since >= STATS_EVERY_US) {
            const uint32_t total = count[0] + count[1] + count[2];
            ESP_LOGI(TAG, "%" PRIu32 " beats (N %" PRIu32 ", S %" PRIu32 ", V %" PRIu32 "), mean HR %.0f bpm; "
                     "slowest inference %" PRId64 " us; %" PRIu32 " failed; fell behind %" PRIu32 " times; "
                     "free heap %" PRIu32 " B (lowest %" PRIu32 " B)",
                     total, count[0], count[1], count[2], total && rr_sum > 0 ? 60.0f * total / rr_sum : 0.0f,
                     worst_us, failed, behind, esp_get_free_heap_size(), esp_get_minimum_free_heap_size());
            count[0] = count[1] = count[2] = failed = behind = 0;
            rr_sum = 0.0f;
            worst_us = 0;
            stats_since = now;
        }
    }
}

esp_err_t edge_model_start(void)
{
    if (ecg_sampler_state() == ECG_STATE_OFF || ecg_sampler_state() == ECG_STATE_ERROR) {
        ESP_LOGW(TAG, "No ECG; the model is not started");
        return ESP_ERR_INVALID_STATE;
    }
    if (!ecg_classifier_init()) {
        ESP_LOGE(TAG, "The model did not load");
        elog_add("MODEL ERROR");
        return ESP_FAIL;
    }
    if (xTaskCreatePinnedToCore(edge_task, "edge_model", 6144, NULL, EDGE_PRIORITY, NULL, 1) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    ESP_LOGI(TAG, "%s: alert on %d of %d beats S or V, at most once per %d s", ECG_MODEL_NAME,
             CONFIG_WEARABLE_EDGE_ALERT_MIN_ABNORMAL, CONFIG_WEARABLE_EDGE_ALERT_WINDOW_BEATS,
             CONFIG_WEARABLE_EDGE_ALERT_COOLDOWN_S);
    return ESP_OK;
}
