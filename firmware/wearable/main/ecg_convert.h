#pragma once

/* ADS1292 sample conversion, with no ESP-IDF dependency so the host test (TC-W07) can build it.
 *
 * In RDATAC mode every DRDY gives a 9-byte frame: a 24-bit status word, then channel 1 and
 * channel 2 as 24-bit two's complement codes, MSB first. A code is turned into microvolts at the
 * electrodes:
 *
 *     uV = code * (2 * VREF / gain) / 2^24
 *
 * The ADS1292 is DC-coupled, so the electrode offset (up to a few hundred mV) is in the signal.
 * A first-order DC blocker (high-pass, ECG_HP_HZ) removes it before the int16 conversion at
 * counts_per_mv; otherwise the offset alone could clamp int16 at 200 counts/mV (+-163 mV). */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ADS1292_FRAME_BYTES 9
#define ADS1292_VREF_UV 2420000 /* internal reference, CONFIG2.VREF_4V = 0 */
#define ADS1292_GAIN 6          /* CH1SET.GAIN1 = 000 */
#define ECG_HP_HZ 0.5f          /* the DC blocker's corner, as monitoring-grade ECG */

/* Status word: 1100, LOFF_STAT[4:0] (RLD, IN2N, IN2P, IN1N, IN1P), GPIO[1:0], 13 zeros. */
#define ADS1292_STATUS_HEADER 0xC00000u
#define ADS1292_STATUS_IN1P_OFF (1u << 15)
#define ADS1292_STATUS_IN1N_OFF (1u << 16)

typedef struct {
    uint32_t status;
    int32_t ch1;
    int32_t ch2;
} ads1292_frame_t;

/* Splits a frame. Returns false when the status word does not start with 1100, which means the
 * frame was not read in step with DRDY (or the wiring is wrong). */
bool ads1292_parse_frame(const uint8_t raw[ADS1292_FRAME_BYTES], ads1292_frame_t *out);

/* 1 if either channel 1 electrode is off (DC lead-off comparators), else 0. */
uint8_t ads1292_ch1_leads_off(uint32_t status);

float ads1292_code_to_uv(int32_t code, int32_t vref_uv, int32_t gain);

typedef struct {
    float a;  /* pole: 1 - 2*pi*fc/fs */
    float x1; /* previous input */
    float y1; /* previous output */
    bool primed;
} ecg_dc_block_t;

void ecg_dc_block_init(ecg_dc_block_t *f, float fc_hz, float fs_hz);
/* The next output: y = x - x1 + a * y1. The first input after init or reset only primes the
 * filter (output 0), so a large electrode offset does not start as a slowly decaying step. */
float ecg_dc_block(ecg_dc_block_t *f, float x);
void ecg_dc_block_reset(ecg_dc_block_t *f);

/* Microvolts to int16 counts at counts_per_mv; rounds half away from zero and clamps. */
int16_t ecg_uv_to_counts(float uv, int32_t counts_per_mv);

/* How many of the n flags are set: the leads-off count of a chunk. */
size_t ecg_count_leads_off(const uint8_t *flags, size_t n);
