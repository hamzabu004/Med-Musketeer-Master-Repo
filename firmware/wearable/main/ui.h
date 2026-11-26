#pragma once

/* The OLED's screens. Once Wi-Fi is set up, the home view is a set of numbered pages that the
 * menu button steps through: 1 ECG, 2 benchmarks, 3 log, 4 gateway. Messages (alerts, connection
 * changes) appear over the current page for a few seconds; pairing screens (QR code, passkey)
 * stay until pairing ends, and the menu button does nothing while they are shown. */

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "qrcode.h"

typedef enum {
    UI_PAGE_ECG,
    UI_PAGE_BENCHMARKS,
    UI_PAGE_LOG,
    UI_PAGE_GATEWAY,
    UI_PAGE_COUNT,
} ui_page_t;

/* What the gateway page shows; filled by the path code (fixed_path.c). */
typedef struct {
    bool wifi;          /* joined and has an IP address */
    bool mqtt;          /* connected to the gateway's broker */
    char ssid[33];
    int rssi;           /* dBm; 0 when unknown */
    char ip[16];
    char gateway[64];   /* broker host:port */
    char status[24];    /* the latest connection message */
} ui_link_t;

typedef void (*ui_link_fn)(ui_link_t *out);

/* After display_init: sets up the menu button and starts the screen task. */
esp_err_t ui_start(void);

void ui_set_link_source(ui_link_fn fn);

/* Pages are the home view only once Wi-Fi is configured; before that the pairing screens are. */
void ui_pages_enable(bool on);

/* Six text lines over the current page for ms milliseconds; ms 0 keeps them until the next
 * message or ui_home (for pairing screens, which the menu button must not hide). */
void ui_message(const char *l1, const char *l2, const char *l3, const char *l4, const char *l5,
                const char *l6, uint32_t ms);

/* The pairing QR code (esp_qrcode display callback). Drawn only while pages are off. */
void ui_qr(esp_qrcode_handle_t qr);

/* Ends any message and shows the current page now. */
void ui_home(void);
