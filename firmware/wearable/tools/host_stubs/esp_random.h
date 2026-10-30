/* Host stand-in for ESP-IDF's esp_random.h; the host test needs distinct ids, not good randomness. */
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

static inline void esp_fill_random(void *buf, size_t len)
{
    for (size_t i = 0; i < len; ++i) ((uint8_t *)buf)[i] = (uint8_t)rand();
}
