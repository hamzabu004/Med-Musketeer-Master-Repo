#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "qrcode.h"

esp_err_t display_init(void);

/* Six full-width text lines (21 characters each). The font has upper-case letters, digits,
 * space and - _ . : / % + >; other characters show as '?'. */
void display_show_text(const char *line1, const char *line2, const char *line3,
                       const char *line4, const char *line5, const char *line6);
void display_show_qr(esp_qrcode_handle_t qr);

/* A menu page (ui.c): a header line with the title and a link icon (filled when connected to the
 * gateway), a rule, and DISPLAY_PAGE_LINES text lines. */
#define DISPLAY_PAGE_LINES 5
#define DISPLAY_PAGE_RULE 10
void display_show_page(const char *title, bool online, const char *const lines[DISPLAY_PAGE_LINES]);

/* The same header over a trace: column x is drawn as a vertical line from row top[x] to
 * bottom[x], each 0 .. DISPLAY_TRACE_ROWS - 1 from the top of the trace area. */
#define DISPLAY_TRACE_COLUMNS 128
#define DISPLAY_TRACE_TOP 12
#define DISPLAY_TRACE_ROWS 52
void display_show_trace_page(const char *title, bool online,
                             const uint8_t top[DISPLAY_TRACE_COLUMNS],
                             const uint8_t bottom[DISPLAY_TRACE_COLUMNS]);
