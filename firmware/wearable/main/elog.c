#include "elog.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"

#define CLOCK_VALID_AFTER 1704067200 /* as fixed_path.c: 2024-01-01, so SNTP has set the clock */

static const char *TAG = "event";

typedef struct {
    time_t at; /* 0 = logged before the clock was set */
    char text[ELOG_TEXT + 1];
} entry_t;

static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static entry_t ring[ELOG_LINES];
static size_t count, next;

void elog_add(const char *fmt, ...)
{
    entry_t e;
    va_list args;
    va_start(args, fmt);
    vsnprintf(e.text, sizeof(e.text), fmt, args);
    va_end(args);
    const time_t now = time(NULL);
    e.at = now >= CLOCK_VALID_AFTER ? now : 0;
    ESP_LOGI(TAG, "%s", e.text);
    taskENTER_CRITICAL(&lock);
    ring[next] = e;
    next = (next + 1) % ELOG_LINES;
    if (count < ELOG_LINES) ++count;
    taskEXIT_CRITICAL(&lock);
}

size_t elog_lines(char out[][ELOG_LINE_LEN], size_t max)
{
    entry_t copy[ELOG_LINES];
    taskENTER_CRITICAL(&lock);
    const size_t n = count < max ? count : max;
    for (size_t i = 0; i < n; ++i) copy[i] = ring[(next + ELOG_LINES - 1 - i) % ELOG_LINES];
    taskEXIT_CRITICAL(&lock);
    for (size_t i = 0; i < n; ++i) {
        if (copy[i].at) {
            struct tm local;
            localtime_r(&copy[i].at, &local);
            snprintf(out[i], ELOG_LINE_LEN, "%02d:%02d %s", local.tm_hour, local.tm_min, copy[i].text);
        } else {
            snprintf(out[i], ELOG_LINE_LEN, "--:-- %s", copy[i].text);
        }
    }
    return n;
}
