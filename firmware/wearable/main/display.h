#pragma once

#include "esp_err.h"
#include "qrcode.h"

esp_err_t display_init(void);
void display_show_text(const char *line1, const char *line2, const char *line3,
                       const char *line4, const char *line5, const char *line6);
void display_show_qr(esp_qrcode_handle_t qr);
