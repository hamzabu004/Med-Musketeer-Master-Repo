#include "ecg_convert.h"

#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static int32_t be24_signed(const uint8_t *b)
{
    uint32_t v = ((uint32_t)b[0] << 16) | ((uint32_t)b[1] << 8) | b[2];
    if (v & 0x800000u) v |= 0xFF000000u; /* sign-extend */
    return (int32_t)v;
}

bool ads1292_parse_frame(const uint8_t raw[ADS1292_FRAME_BYTES], ads1292_frame_t *out)
{
    out->status = ((uint32_t)raw[0] << 16) | ((uint32_t)raw[1] << 8) | raw[2];
    out->ch1 = be24_signed(raw + 3);
    out->ch2 = be24_signed(raw + 6);
    return (out->status & 0xF00000u) == ADS1292_STATUS_HEADER;
}

uint8_t ads1292_ch1_leads_off(uint32_t status)
{
    return (status & (ADS1292_STATUS_IN1P_OFF | ADS1292_STATUS_IN1N_OFF)) ? 1 : 0;
}

float ads1292_code_to_uv(int32_t code, int32_t vref_uv, int32_t gain)
{
    return (float)((double)code * (2.0 * vref_uv / gain) / 16777216.0);
}

void ecg_dc_block_init(ecg_dc_block_t *f, float fc_hz, float fs_hz)
{
    f->a = 1.0f - 2.0f * (float)M_PI * fc_hz / fs_hz;
    ecg_dc_block_reset(f);
}

void ecg_dc_block_reset(ecg_dc_block_t *f)
{
    f->x1 = 0.0f;
    f->y1 = 0.0f;
    f->primed = false;
}

float ecg_dc_block(ecg_dc_block_t *f, float x)
{
    if (!f->primed) {
        f->x1 = x;
        f->y1 = 0.0f;
        f->primed = true;
        return 0.0f;
    }
    const float y = x - f->x1 + f->a * f->y1;
    f->x1 = x;
    f->y1 = y;
    return y;
}

int16_t ecg_uv_to_counts(float uv, int32_t counts_per_mv)
{
    const double c = (double)uv * counts_per_mv / 1000.0;
    const double r = c >= 0 ? floor(c + 0.5) : -floor(-c + 0.5);
    if (r > INT16_MAX) return INT16_MAX;
    if (r < INT16_MIN) return INT16_MIN;
    return (int16_t)r;
}

size_t ecg_count_leads_off(const uint8_t *flags, size_t n)
{
    size_t count = 0;
    for (size_t i = 0; i < n; ++i) count += flags[i] != 0;
    return count;
}
