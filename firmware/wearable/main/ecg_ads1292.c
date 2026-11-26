/* ADS1292 front end over SPI2: channel 1 at 500 SPS in continuous read mode (RDATAC), internal
 * 2.42 V reference, PGA gain 6, right-leg drive from channel 1, DC lead-off detection on both
 * channel 1 inputs. Channel 2 is powered down. Pins are under "ADS1292 pins" in menuconfig.
 *
 * DRDY falls every 2 ms; its interrupt gives a counting semaphore and read() fetches one 9-byte
 * frame per DRDY. The ADS1292 has no FIFO: a frame not read before the next DRDY is lost. read()
 * counts those (the semaphore held more than one) and the sampler's rate log shows them. */
#include <inttypes.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "ecg_convert.h"
#include "ecg_frontend.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#define FS_HZ 500
#define COUNTS_PER_MV 200 /* the dashboard's and MIT-BIH's scale: 5 uV per count */
#define SPI_HZ 1000000    /* well under the 20 MHz limit; a frame takes 72 us */
#define DRDY_PENDING_MAX 8

/* Opcodes and registers (ADS1292 datasheet, 9.5 and 9.6). */
#define CMD_RESET 0x06
#define CMD_START 0x08
#define CMD_STOP 0x0A
#define CMD_RDATAC 0x10
#define CMD_SDATAC 0x11
#define CMD_RREG 0x20
#define CMD_WREG 0x40

#define REG_ID 0x00
#define REG_CONFIG1 0x01

/* CONFIG1 .. RESP2, written in one WREG and read back to check the wiring. */
static const uint8_t config_regs[] = {
    0x02, /* CONFIG1: continuous conversion, 500 SPS */
    0xE0, /* CONFIG2: lead-off comparators on, reference buffer on, VREF 2.42 V, no clock out */
    0x10, /* LOFF: comparator threshold 95 %, 6 nA DC lead-off current */
    0x00, /* CH1SET: powered up, gain 6, normal electrode input */
    0x81, /* CH2SET: powered down, input shorted */
    0x23, /* RLD_SENS: RLD buffer on, derived from IN1P and IN1N */
    0x03, /* LOFF_SENS: lead-off detection on IN1P and IN1N */
    0x00, /* LOFF_STAT: fCLK = 512 kHz (internal oscillator) */
    0x02, /* RESP1: no respiration; bit 1 must be 1 */
    0x03, /* RESP2: RLD reference generated internally; bit 0 must be 1 */
};

static const char *TAG = "ecg_ads1292";

static spi_device_handle_t spi;
static SemaphoreHandle_t drdy;
static ecg_dc_block_t dc_block;
static bool was_off;
static volatile uint32_t lost_frames;
static uint32_t bad_frames;

static void IRAM_ATTR drdy_isr(void *arg)
{
    (void)arg;
    BaseType_t woken = pdFALSE;
    xSemaphoreGiveFromISR(drdy, &woken);
    portYIELD_FROM_ISR(woken);
}

static void cs(bool active)
{
    gpio_set_level(CONFIG_WEARABLE_ECG_SPI_CS_GPIO, active ? 0 : 1);
}

static esp_err_t xfer(const uint8_t *tx, uint8_t *rx, size_t len)
{
    spi_transaction_t t = {.length = len * 8, .tx_buffer = tx, .rx_buffer = rx};
    return spi_device_polling_transmit(spi, &t);
}

/* Sends bytes one at a time inside one CS-low period, at least 4 tCLK (7.8 us at 512 kHz) apart,
 * as multi-byte commands need (tSDECODE). rx may be NULL. */
static esp_err_t command(const uint8_t *tx, uint8_t *rx, size_t len)
{
    esp_err_t err = ESP_OK;
    cs(true);
    esp_rom_delay_us(2);
    for (size_t i = 0; i < len && err == ESP_OK; ++i) {
        uint8_t in = 0;
        err = xfer(&tx[i], &in, 1);
        if (rx) rx[i] = in;
        esp_rom_delay_us(10);
    }
    cs(false);
    esp_rom_delay_us(10);
    return err;
}

static esp_err_t opcode(uint8_t op)
{
    return command(&op, NULL, 1);
}

static esp_err_t read_regs(uint8_t first, uint8_t *out, size_t n)
{
    uint8_t tx[2 + sizeof(config_regs) + 1] = {(uint8_t)(CMD_RREG | first), (uint8_t)(n - 1)};
    uint8_t rx[sizeof(tx)];
    if (n > sizeof(tx) - 2) return ESP_ERR_INVALID_SIZE;
    esp_err_t err = command(tx, rx, 2 + n);
    if (err == ESP_OK) memcpy(out, rx + 2, n);
    return err;
}

static esp_err_t write_regs(uint8_t first, const uint8_t *values, size_t n)
{
    uint8_t tx[2 + sizeof(config_regs)] = {(uint8_t)(CMD_WREG | first), (uint8_t)(n - 1)};
    if (n > sizeof(tx) - 2) return ESP_ERR_INVALID_SIZE;
    memcpy(tx + 2, values, n);
    return command(tx, NULL, 2 + n);
}

static esp_err_t ads_init(void)
{
    const gpio_config_t outputs = {
        .pin_bit_mask = (1ULL << CONFIG_WEARABLE_ECG_SPI_CS_GPIO) |
                        (1ULL << CONFIG_WEARABLE_ECG_START_GPIO) |
                        (1ULL << CONFIG_WEARABLE_ECG_PWDN_GPIO),
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&outputs), TAG, "output pins");
    cs(false);
    gpio_set_level(CONFIG_WEARABLE_ECG_START_GPIO, 0);
    gpio_set_level(CONFIG_WEARABLE_ECG_PWDN_GPIO, 1);

    const spi_bus_config_t bus = {
        .sclk_io_num = CONFIG_WEARABLE_ECG_SPI_SCLK_GPIO,
        .mosi_io_num = CONFIG_WEARABLE_ECG_SPI_MOSI_GPIO,
        .miso_io_num = CONFIG_WEARABLE_ECG_SPI_MISO_GPIO,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 32,
    };
    ESP_RETURN_ON_ERROR(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_DISABLED), TAG, "SPI bus");
    const spi_device_interface_config_t dev = {
        .mode = 1, /* CPOL 0, CPHA 1 */
        .clock_speed_hz = SPI_HZ,
        .spics_io_num = -1, /* CS is held by hand across multi-byte commands */
        .queue_size = 1,
    };
    ESP_RETURN_ON_ERROR(spi_bus_add_device(SPI2_HOST, &dev, &spi), TAG, "SPI device");

    /* Power-on: wait out tPOR (2^18 tCLK, about 0.5 s), then a reset pulse on PWDN/RESET. */
    vTaskDelay(pdMS_TO_TICKS(600));
    gpio_set_level(CONFIG_WEARABLE_ECG_PWDN_GPIO, 0);
    esp_rom_delay_us(50);
    gpio_set_level(CONFIG_WEARABLE_ECG_PWDN_GPIO, 1);
    vTaskDelay(pdMS_TO_TICKS(10));
    /* The device wakes up in RDATAC, which ignores register commands. */
    ESP_RETURN_ON_ERROR(opcode(CMD_SDATAC), TAG, "SDATAC");

    uint8_t id = 0;
    ESP_RETURN_ON_ERROR(read_regs(REG_ID, &id, 1), TAG, "read ID");
    if (id != 0x53 && id != 0x73) { /* ADS1292, ADS1292R */
        ESP_LOGE(TAG, "Unexpected ID 0x%02x (want 0x53 for the ADS1292); check the SPI wiring", id);
        return ESP_ERR_NOT_FOUND;
    }
    ESP_RETURN_ON_ERROR(write_regs(REG_CONFIG1, config_regs, sizeof(config_regs)), TAG, "WREG");
    uint8_t back[sizeof(config_regs)];
    ESP_RETURN_ON_ERROR(read_regs(REG_CONFIG1, back, sizeof(back)), TAG, "RREG");
    for (size_t i = 0; i < sizeof(back); ++i) {
        /* LOFF_STAT's low bits are live lead-off flags, not configuration. */
        const uint8_t mask = (REG_CONFIG1 + i == 0x08) ? 0x40 : 0xFF;
        if ((back[i] & mask) != (config_regs[i] & mask)) {
            ESP_LOGE(TAG, "Register 0x%02x reads 0x%02x, wrote 0x%02x", (unsigned)(REG_CONFIG1 + i),
                     back[i], config_regs[i]);
            return ESP_ERR_INVALID_RESPONSE;
        }
    }
    vTaskDelay(pdMS_TO_TICKS(150)); /* reference buffer settling */

    drdy = xSemaphoreCreateCounting(DRDY_PENDING_MAX, 0);
    if (!drdy) return ESP_ERR_NO_MEM;
    const gpio_config_t in = {
        .pin_bit_mask = 1ULL << CONFIG_WEARABLE_ECG_DRDY_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&in), TAG, "DRDY pin");
    const esp_err_t isr = gpio_install_isr_service(0);
    if (isr != ESP_OK && isr != ESP_ERR_INVALID_STATE) return isr; /* already installed is fine */
    ESP_RETURN_ON_ERROR(gpio_isr_handler_add(CONFIG_WEARABLE_ECG_DRDY_GPIO, drdy_isr, NULL), TAG, "DRDY ISR");

    ecg_dc_block_init(&dc_block, ECG_HP_HZ, FS_HZ);
    ESP_LOGI(TAG, "ADS1292 (ID 0x%02x) configured: %d SPS, gain %d, lead-off on CH1", id, FS_HZ,
             ADS1292_GAIN);
    return ESP_OK;
}

static esp_err_t ads_start(void)
{
    ESP_RETURN_ON_ERROR(opcode(CMD_RDATAC), TAG, "RDATAC");
    xQueueReset(drdy);
    ecg_dc_block_reset(&dc_block);
    gpio_set_level(CONFIG_WEARABLE_ECG_START_GPIO, 1);
    return ESP_OK;
}

static esp_err_t ads_stop(void)
{
    gpio_set_level(CONFIG_WEARABLE_ECG_START_GPIO, 0);
    return opcode(CMD_SDATAC);
}

static size_t ads_read(int16_t *out, uint8_t *leads_off, size_t max, TickType_t timeout)
{
    static const uint8_t zeros[ADS1292_FRAME_BYTES];
    static uint8_t raw[ADS1292_FRAME_BYTES];
    size_t n = 0;
    const TickType_t begin = xTaskGetTickCount();
    while (n < max) {
        const TickType_t waited = xTaskGetTickCount() - begin;
        /* Once a sample is in hand, return as soon as no further one is waiting. */
        const TickType_t wait = n ? 0 : (waited < timeout ? timeout - waited : 0);
        if (xSemaphoreTake(drdy, wait) != pdTRUE) break;
        const UBaseType_t behind = uxSemaphoreGetCount(drdy);
        if (behind) { /* only the newest frame is readable; the others were overwritten */
            lost_frames += behind;
            for (UBaseType_t i = 0; i < behind; ++i) xSemaphoreTake(drdy, 0);
        }
        cs(true);
        const esp_err_t err = xfer(zeros, raw, sizeof(raw));
        cs(false);
        ads1292_frame_t f;
        if (err != ESP_OK || !ads1292_parse_frame(raw, &f)) {
            if (++bad_frames % 500 == 1) ESP_LOGW(TAG, "Bad frame (%" PRIu32 " so far)", bad_frames);
            continue;
        }
        const uint8_t off = ads1292_ch1_leads_off(f.status);
        if (was_off && !off) ecg_dc_block_reset(&dc_block); /* electrodes back on: a new offset */
        was_off = off;
        const float uv = ads1292_code_to_uv(f.ch1, ADS1292_VREF_UV, ADS1292_GAIN);
        out[n] = off ? 0 : ecg_uv_to_counts(ecg_dc_block(&dc_block, uv), COUNTS_PER_MV);
        leads_off[n] = off;
        ++n;
    }
    return n;
}

static uint32_t ads_lost(void)
{
    const uint32_t lost = lost_frames;
    lost_frames = 0;
    return lost;
}

const ecg_frontend_t ecg_frontend_ads1292 = {
    .sensor = "ADS1292",
    .lead = CONFIG_WEARABLE_ECG_LEAD,
    .fs_hz = FS_HZ,
    .counts_per_mv = COUNTS_PER_MV,
    .init = ads_init,
    .start = ads_start,
    .stop = ads_stop,
    .read = ads_read,
    .take_lost = ads_lost,
};
