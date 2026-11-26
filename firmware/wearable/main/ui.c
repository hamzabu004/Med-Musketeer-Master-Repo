#include "ui.h"

#include <stdio.h>
#include <string.h>

#include "display.h"
#include "elog.h"
#include "driver/gpio.h"
#include "ecg_sampler.h"
#include "edge_model.h"
#include "esp_heap_caps.h"
#include "esp_image_format.h"
#include "esp_ota_ops.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#define TICK_MS 100          /* the ECG page's redraw period */
#define SLOW_PAGE_MS 1000    /* the other pages' */
#define DEBOUNCE_MS 30
#define PRESS_GAP_MS 250     /* presses closer than this count once */
#define PRESS_BIT (1u << 0)
#define REDRAW_BIT (1u << 1)
#define UI_PRIORITY 3

#define TRACE_PER_COLUMN 10  /* samples per pixel column: 128 columns show 2.56 s at 500 SPS */
#define TRACE_MIN_SPAN 100   /* counts (0.5 mV): smaller signals are centred, not stretched */

static const char *TAG = "ui";
static const char *const titles[UI_PAGE_COUNT] = {"ECG", "BENCHMARKS", "LOG", "GATEWAY"};

static SemaphoreHandle_t lock;   /* guards the state below and every draw */
static TaskHandle_t task;
static bool pages_on;
static bool sticky;              /* a pairing screen is up */
static int64_t message_until_us; /* a timed message is up until then; 0 = none */
static ui_page_t page;
static volatile ui_link_fn link_source;

static void IRAM_ATTR menu_isr(void *arg)
{
    (void)arg;
    BaseType_t woken = pdFALSE;
    if (task) xTaskNotifyFromISR(task, PRESS_BIT, eSetBits, &woken);
    portYIELD_FROM_ISR(woken);
}

static void link(ui_link_t *out)
{
    memset(out, 0, sizeof(*out));
    const ui_link_fn fn = link_source;
    if (fn) fn(out);
}

static void header(char *buf, size_t len, const char *extra)
{
    snprintf(buf, len, "%d/%d %s%s%s", (int)page + 1, UI_PAGE_COUNT, titles[page], extra ? " " : "",
             extra ? extra : "");
}

static void draw_text_page(bool online, const char *l1, const char *l2, const char *l3,
                           const char *l4, const char *l5)
{
    char title[24];
    header(title, sizeof(title), NULL);
    const char *const lines[DISPLAY_PAGE_LINES] = {l1, l2, l3, l4, l5};
    display_show_page(title, online, lines);
}

static void draw_ecg(bool online)
{
    static int16_t samples[DISPLAY_TRACE_COLUMNS * TRACE_PER_COLUMN];
    static uint8_t top[DISPLAY_TRACE_COLUMNS], bottom[DISPLAY_TRACE_COLUMNS];
    const ecg_state_t state = ecg_sampler_state();
    if (state == ECG_STATE_ERROR || state == ECG_STATE_OFF) {
        draw_text_page(online, "ECG ERROR", "", "CHECK THE ADS1292", "WIRING AND POWER", "");
        return;
    }
    const size_t want = sizeof(samples) / sizeof(samples[0]);
    const uint64_t head = ecg_sampler_head();
    if (head < want || ecg_sampler_copy(head - want, want, samples, NULL) != want) {
        draw_text_page(online, "STARTING...", "", "", "", "");
        return;
    }
    int lo = INT16_MAX, hi = INT16_MIN;
    int16_t col_min[DISPLAY_TRACE_COLUMNS], col_max[DISPLAY_TRACE_COLUMNS];
    for (int x = 0; x < DISPLAY_TRACE_COLUMNS; ++x) {
        int16_t mn = INT16_MAX, mx = INT16_MIN;
        for (int i = 0; i < TRACE_PER_COLUMN; ++i) {
            const int16_t v = samples[x * TRACE_PER_COLUMN + i];
            if (v < mn) mn = v;
            if (v > mx) mx = v;
        }
        col_min[x] = mn;
        col_max[x] = mx;
        if (mn < lo) lo = mn;
        if (mx > hi) hi = mx;
    }
    int span = hi - lo;
    if (span < TRACE_MIN_SPAN) {
        lo -= (TRACE_MIN_SPAN - span) / 2;
        span = TRACE_MIN_SPAN;
    }
    for (int x = 0; x < DISPLAY_TRACE_COLUMNS; ++x) { /* higher values higher on screen */
        top[x] = (uint8_t)((lo + span - col_max[x]) * (DISPLAY_TRACE_ROWS - 1) / span);
        bottom[x] = (uint8_t)((lo + span - col_min[x]) * (DISPLAY_TRACE_ROWS - 1) / span);
    }

    char extra[16] = "";
    edge_status_t st;
    if (state == ECG_STATE_LEADS_OFF) {
        snprintf(extra, sizeof(extra), "LEADS OFF");
    } else if (edge_model_status(&st) && st.bpm > 0.0f) {
        snprintf(extra, sizeof(extra), "%d BPM %c", (int)(st.bpm + 0.5f), st.last);
    }
    char title[24];
    header(title, sizeof(title), extra[0] ? extra : NULL);
    display_show_trace_page(title, online, top, bottom);
}

static void draw_gateway(const ui_link_t *l)
{
    char wifi[24], signal[24], ip[24], gw[24];
    if (l->ssid[0]) snprintf(wifi, sizeof(wifi), "WIFI %.16s", l->ssid);
    else snprintf(wifi, sizeof(wifi), "WIFI NOT SET UP");
    if (l->wifi && l->rssi) snprintf(signal, sizeof(signal), "SIGNAL %d DBM", l->rssi);
    else snprintf(signal, sizeof(signal), "SIGNAL --");
    snprintf(ip, sizeof(ip), "IP %s", l->wifi && l->ip[0] ? l->ip : "--");
    snprintf(gw, sizeof(gw), "GW %.18s", l->gateway[0] ? l->gateway : "--");
    draw_text_page(l->mqtt, wifi, signal, ip, l->status[0] ? l->status : "", gw);
}

/* The app's size in flash and its partition's, read once at start. */
static uint32_t app_bytes, partition_bytes;

static void read_flash_use(void)
{
    const esp_partition_t *part = esp_ota_get_running_partition();
    if (!part) return;
    partition_bytes = part->size;
    const esp_partition_pos_t pos = {.offset = part->address, .size = part->size};
    esp_image_metadata_t meta;
    if (esp_image_get_metadata(&pos, &meta) == ESP_OK) app_bytes = meta.image_len;
}

/* CPU use per core over the time since the last call (about a second): 100 % minus the share
 * its idle task ran. -1 until there are two readings, or without FreeRTOS run-time stats. */
static void cpu_use(int pct[2])
{
    pct[0] = pct[1] = -1;
#if CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS
    static uint64_t idle_prev[2];
    static int64_t at_prev;
    const int64_t now = esp_timer_get_time();
    uint64_t idle[2];
    for (int c = 0; c < 2; ++c) idle[c] = ulTaskGetIdleRunTimeCounterForCore(c);
    if (at_prev && now > at_prev) {
        for (int c = 0; c < 2; ++c) {
            const double share = (double)(idle[c] - idle_prev[c]) / (double)(now - at_prev);
            const int busy = (int)(100.0 * (1.0 - share) + 0.5);
            pct[c] = busy < 0 ? 0 : busy > 100 ? 100 : busy;
        }
    }
    idle_prev[0] = idle[0];
    idle_prev[1] = idle[1];
    at_prev = now;
#endif
}

static void draw_benchmarks(bool online)
{
    char ram[48], flash[48], cpu[48], infer[48]; /* the display cuts each at 21 characters */
    const size_t total = heap_caps_get_total_size(MALLOC_CAP_INTERNAL);
    const size_t free_b = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    snprintf(ram, sizeof(ram), "RAM %u/%u KB USED", (unsigned)((total - free_b) / 1024),
             (unsigned)(total / 1024));
    if (partition_bytes) {
        snprintf(flash, sizeof(flash), "FLASH %.2f/%.2f MB", app_bytes / 1048576.0,
                 partition_bytes / 1048576.0);
    } else {
        snprintf(flash, sizeof(flash), "FLASH --");
    }
    int pct[2];
    cpu_use(pct);
    if (pct[0] >= 0) snprintf(cpu, sizeof(cpu), "CPU C0 %d%% C1 %d%%", pct[0], pct[1]);
    else snprintf(cpu, sizeof(cpu), "CPU --");
    edge_status_t st;
    edge_model_status(&st);
    if (st.infer_us_avg) {
        snprintf(infer, sizeof(infer), "INFER %u US MAX %u", (unsigned)st.infer_us_avg,
                 (unsigned)st.infer_us_max);
    } else {
        snprintf(infer, sizeof(infer), "INFER --");
    }
    draw_text_page(online, ram, flash, cpu, infer, "CURRENT NO SENSOR");
}

static void draw_log(bool online)
{
    char lines[ELOG_LINES][ELOG_LINE_LEN];
    const size_t n = elog_lines(lines, ELOG_LINES);
    const char *l[DISPLAY_PAGE_LINES] = {"", "", "", "", ""};
    for (size_t i = 0; i < n && i < DISPLAY_PAGE_LINES; ++i) l[i] = lines[i];
    if (!n) l[1] = "NO EVENTS YET";
    draw_text_page(online, l[0], l[1], l[2], l[3], l[4]);
}

static void draw_page(void)
{
    ui_link_t l;
    link(&l);
    switch (page) {
    case UI_PAGE_ECG: draw_ecg(l.mqtt); break;
    case UI_PAGE_BENCHMARKS: draw_benchmarks(l.mqtt); break;
    case UI_PAGE_LOG: draw_log(l.mqtt); break;
    case UI_PAGE_GATEWAY: draw_gateway(&l); break;
    default: break;
    }
}

/* Under lock: may a page be drawn now? Ends a timed message whose time is up. */
static bool page_showing(void)
{
    if (!pages_on || sticky) return false;
    if (message_until_us) {
        if (esp_timer_get_time() < message_until_us) return false;
        message_until_us = 0;
    }
    return true;
}

static void ui_task(void *arg)
{
    (void)arg;
    int64_t last_press_us = 0, last_slow_us = 0;
    bool was_showing = false;
    for (;;) {
        uint32_t bits = 0;
        xTaskNotifyWait(0, UINT32_MAX, &bits, pdMS_TO_TICKS(TICK_MS));
        bool force = (bits & REDRAW_BIT) != 0;

        if (bits & PRESS_BIT) {
            vTaskDelay(pdMS_TO_TICKS(DEBOUNCE_MS));
            const int64_t now = esp_timer_get_time();
            if (gpio_get_level(CONFIG_WEARABLE_MENU_BUTTON_GPIO) == 0 &&
                now - last_press_us >= PRESS_GAP_MS * 1000LL) {
                last_press_us = now;
                xSemaphoreTake(lock, portMAX_DELAY);
                if (pages_on && !sticky) {
                    if (message_until_us && now < message_until_us) message_until_us = 0; /* dismiss */
                    else page = (ui_page_t)((page + 1) % UI_PAGE_COUNT);
                    ESP_LOGI(TAG, "Page %d: %s", (int)page + 1, titles[page]);
                    force = true;
                }
                xSemaphoreGive(lock);
            }
        }

        xSemaphoreTake(lock, portMAX_DELAY);
        const bool showing = page_showing();
        const int64_t now = esp_timer_get_time();
        if (showing && (force || !was_showing || page == UI_PAGE_ECG ||
                        now - last_slow_us >= SLOW_PAGE_MS * 1000LL)) {
            draw_page();
            last_slow_us = now;
        }
        was_showing = showing;
        xSemaphoreGive(lock);
    }
}

esp_err_t ui_start(void)
{
    lock = xSemaphoreCreateMutex();
    if (!lock) return ESP_ERR_NO_MEM;
    read_flash_use();
    const gpio_config_t button = {
        .pin_bit_mask = 1ULL << CONFIG_WEARABLE_MENU_BUTTON_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    esp_err_t err = gpio_config(&button);
    if (err != ESP_OK) return err;
    err = gpio_install_isr_service(0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) return err; /* already installed is fine */
    if (xTaskCreate(ui_task, "ui", 4096, NULL, UI_PRIORITY, &task) != pdPASS) return ESP_ERR_NO_MEM;
    return gpio_isr_handler_add(CONFIG_WEARABLE_MENU_BUTTON_GPIO, menu_isr, NULL);
}

void ui_set_link_source(ui_link_fn fn)
{
    link_source = fn;
}

static void redraw_soon(void)
{
    if (task) xTaskNotify(task, REDRAW_BIT, eSetBits);
}

void ui_pages_enable(bool on)
{
    if (!lock) return;
    xSemaphoreTake(lock, portMAX_DELAY);
    pages_on = on;
    if (on) sticky = false; /* a configuration has been applied: pairing is over */
    xSemaphoreGive(lock);
    redraw_soon();
}

void ui_message(const char *l1, const char *l2, const char *l3, const char *l4, const char *l5,
                const char *l6, uint32_t ms)
{
    if (!lock) {
        display_show_text(l1, l2, l3, l4, l5, l6);
        return;
    }
    xSemaphoreTake(lock, portMAX_DELAY);
    sticky = ms == 0;
    message_until_us = ms ? esp_timer_get_time() + (int64_t)ms * 1000 : 0;
    display_show_text(l1, l2, l3, l4, l5, l6);
    xSemaphoreGive(lock);
}

void ui_qr(esp_qrcode_handle_t qr)
{
    if (!lock) {
        display_show_qr(qr);
        return;
    }
    xSemaphoreTake(lock, portMAX_DELAY);
    if (!pages_on) {
        sticky = true;
        message_until_us = 0;
        display_show_qr(qr);
    }
    xSemaphoreGive(lock);
}

void ui_home(void)
{
    if (!lock) return;
    xSemaphoreTake(lock, portMAX_DELAY);
    sticky = false;
    message_until_us = 0;
    xSemaphoreGive(lock);
    redraw_soon();
}
