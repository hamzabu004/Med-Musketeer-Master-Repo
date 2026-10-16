#include <ctype.h>
#include <string.h>

#include "driver/i2c_master.h"
#include "esp_check.h"
#include "esp_lcd_io_i2c.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_sh1106.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#include "display.h"

#define OLED_WIDTH 128
#define OLED_HEIGHT 64
static const char *TAG = "oled";
static esp_lcd_panel_handle_t panel;
static SemaphoreHandle_t display_mutex;
static uint8_t framebuffer[OLED_WIDTH * OLED_HEIGHT / 8];

static const uint8_t *glyph(char c)
{
    static const uint8_t blank[5] = {0};
    static const uint8_t question[5] = {0x02, 0x01, 0x51, 0x09, 0x06};
    static const uint8_t digits[10][5] = {
        {0x3e,0x51,0x49,0x45,0x3e}, {0x00,0x42,0x7f,0x40,0x00},
        {0x42,0x61,0x51,0x49,0x46}, {0x21,0x41,0x45,0x4b,0x31},
        {0x18,0x14,0x12,0x7f,0x10}, {0x27,0x45,0x45,0x45,0x39},
        {0x3c,0x4a,0x49,0x49,0x30}, {0x01,0x71,0x09,0x05,0x03},
        {0x36,0x49,0x49,0x49,0x36}, {0x06,0x49,0x49,0x29,0x1e},
    };
    static const uint8_t letters[26][5] = {
        {0x7e,0x11,0x11,0x11,0x7e}, {0x7f,0x49,0x49,0x49,0x36},
        {0x3e,0x41,0x41,0x41,0x22}, {0x7f,0x41,0x41,0x22,0x1c},
        {0x7f,0x49,0x49,0x49,0x41}, {0x7f,0x09,0x09,0x09,0x01},
        {0x3e,0x41,0x49,0x49,0x7a}, {0x7f,0x08,0x08,0x08,0x7f},
        {0x00,0x41,0x7f,0x41,0x00}, {0x20,0x40,0x41,0x3f,0x01},
        {0x7f,0x08,0x14,0x22,0x41}, {0x7f,0x40,0x40,0x40,0x40},
        {0x7f,0x02,0x0c,0x02,0x7f}, {0x7f,0x04,0x08,0x10,0x7f},
        {0x3e,0x41,0x41,0x41,0x3e}, {0x7f,0x09,0x09,0x09,0x06},
        {0x3e,0x41,0x51,0x21,0x5e}, {0x7f,0x09,0x19,0x29,0x46},
        {0x46,0x49,0x49,0x49,0x31}, {0x01,0x01,0x7f,0x01,0x01},
        {0x3f,0x40,0x40,0x40,0x3f}, {0x1f,0x20,0x40,0x20,0x1f},
        {0x3f,0x40,0x38,0x40,0x3f}, {0x63,0x14,0x08,0x14,0x63},
        {0x07,0x08,0x70,0x08,0x07}, {0x61,0x51,0x49,0x45,0x43},
    };

    c = (char)toupper((unsigned char)c);
    if (c >= '0' && c <= '9') return digits[c - '0'];
    if (c >= 'A' && c <= 'Z') return letters[c - 'A'];
    switch (c) {
    case ' ': return blank;
    case '-': { static const uint8_t g[5] = {0x08,0x08,0x08,0x08,0x08}; return g; }
    case '_': { static const uint8_t g[5] = {0x40,0x40,0x40,0x40,0x40}; return g; }
    case '.': { static const uint8_t g[5] = {0,0x60,0x60,0,0}; return g; }
    case ':': { static const uint8_t g[5] = {0,0x36,0x36,0,0}; return g; }
    case '/': { static const uint8_t g[5] = {0x20,0x10,0x08,0x04,0x02}; return g; }
    default: return question;
    }
}

static void pixel_set(int x, int y, bool on)
{
    if (x < 0 || x >= OLED_WIDTH || y < 0 || y >= OLED_HEIGHT) return;
    size_t index = (size_t)(y / 8) * OLED_WIDTH + x;
    uint8_t mask = (uint8_t)(1U << (y % 8));
    if (on) framebuffer[index] |= mask;
    else framebuffer[index] &= (uint8_t)~mask;
}

static void draw_char(int x, int y, char c)
{
    const uint8_t *bits = glyph(c);
    for (int col = 0; col < 5; ++col) {
        for (int row = 0; row < 7; ++row) {
            if (bits[col] & (1U << row)) pixel_set(x + col, y + row, true);
        }
    }
}

static void draw_text(int x, int y, const char *text)
{
    if (!text) return;
    for (size_t i = 0; text[i] && x + 5 < OLED_WIDTH; ++i, x += 6) {
        draw_char(x, y, text[i]);
    }
}

static void flush(void)
{
    ESP_ERROR_CHECK(esp_lcd_panel_draw_bitmap(panel, 0, 0, OLED_WIDTH, OLED_HEIGHT,
                                             framebuffer));
}

esp_err_t display_init(void)
{
    i2c_master_bus_handle_t bus = NULL;
    i2c_master_bus_config_t bus_config = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .i2c_port = 0,
        .sda_io_num = CONFIG_GATEWAY_OLED_SDA_GPIO,
        .scl_io_num = CONFIG_GATEWAY_OLED_SCL_GPIO,
        .flags.enable_internal_pullup = true,
    };
    ESP_RETURN_ON_ERROR(i2c_new_master_bus(&bus_config, &bus), TAG, "I2C bus init failed");

    esp_lcd_panel_io_handle_t io = NULL;
    esp_lcd_panel_io_i2c_config_t io_config = {
        .dev_addr = CONFIG_GATEWAY_OLED_I2C_ADDRESS,
        .scl_speed_hz = 400000,
        .transaction_timeout_ms = 100,
        .control_phase_bytes = 1,
        .dc_bit_offset = 6,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
    };
    ESP_RETURN_ON_ERROR(esp_lcd_new_panel_io_i2c(bus, &io_config, &io), TAG,
                        "OLED I2C IO init failed");

    esp_lcd_panel_dev_config_t panel_config = {
        .bits_per_pixel = 1,
        .reset_gpio_num = -1,
    };
    ESP_RETURN_ON_ERROR(esp_lcd_new_panel_sh1106(io, &panel_config, &panel), TAG,
                        "SH1106 init failed");
    ESP_RETURN_ON_ERROR(esp_lcd_panel_reset(panel), TAG, "OLED reset failed");
    ESP_RETURN_ON_ERROR(esp_lcd_panel_init(panel), TAG, "OLED panel init failed");
    ESP_RETURN_ON_ERROR(esp_lcd_panel_disp_on_off(panel, true), TAG, "OLED enable failed");
    display_mutex = xSemaphoreCreateMutex();
    ESP_RETURN_ON_FALSE(display_mutex, ESP_ERR_NO_MEM, TAG, "display mutex allocation failed");
    memset(framebuffer, 0, sizeof(framebuffer));
    flush();
    return ESP_OK;
}

void display_show_text(const char *line1, const char *line2, const char *line3,
                       const char *line4, const char *line5, const char *line6)
{
    const char *lines[] = {line1, line2, line3, line4, line5, line6};
    if (!display_mutex || xSemaphoreTake(display_mutex, portMAX_DELAY) != pdTRUE) return;
    memset(framebuffer, 0, sizeof(framebuffer));
    for (size_t i = 0; i < 6; ++i) draw_text(2, (int)i * 10 + 1, lines[i]);
    flush();
    xSemaphoreGive(display_mutex);
}

void display_show_qr(esp_qrcode_handle_t qr)
{
    if (!display_mutex || xSemaphoreTake(display_mutex, portMAX_DELAY) != pdTRUE) return;
    int size = esp_qrcode_get_size(qr);
    int quiet = 4;
    int module_count = size + quiet * 2;
    int scale = (OLED_HEIGHT - 2) / module_count;
    if (scale < 1) scale = 1;
    int drawn = module_count * scale;
    int left = (OLED_WIDTH - drawn) / 2;
    int top = (OLED_HEIGHT - drawn) / 2;

    memset(framebuffer, 0xFF, sizeof(framebuffer));
    for (int y = 0; y < size; ++y) {
        for (int x = 0; x < size; ++x) {
            if (!esp_qrcode_get_module(qr, x, y)) continue;
            for (int dy = 0; dy < scale; ++dy) {
                for (int dx = 0; dx < scale; ++dx) {
                    pixel_set(left + (x + quiet) * scale + dx,
                             top + (y + quiet) * scale + dy, false);
                }
            }
        }
    }
    flush();
    xSemaphoreGive(display_mutex);
}
