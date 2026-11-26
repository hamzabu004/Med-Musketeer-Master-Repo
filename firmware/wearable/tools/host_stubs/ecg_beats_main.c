/* Host build of main/ecg_beats.c for test_ecg_beats.py (TC-W08). Reads 500 Hz samples from stdin
 * as little-endian int16 counts, each followed by one leads-off byte, and prints one line per
 * beat: "<r> <pre_rr_s> <rr0> <rr1> <rr2> <rr3> <win0> ... <win63>". The first argument is the
 * counts per mV (default 200). */
#include <stdio.h>
#include <stdlib.h>

#include "ecg_beats.h"

int main(int argc, char **argv)
{
    static ecg_beats_t b;
    static ecg_beat_t beats[8];
    ecg_beats_init(&b, argc > 1 ? (float)atof(argv[1]) : 200.0f);
    unsigned char rec[3];
    while (fread(rec, 1, sizeof(rec), stdin) == sizeof(rec)) {
        const int16_t v = (int16_t)(rec[0] | (rec[1] << 8));
        const uint8_t off = rec[2];
        const size_t n = ecg_beats_push(&b, &v, &off, 1, beats, 8);
        for (size_t i = 0; i < n; ++i) {
            printf("%llu %.6f", (unsigned long long)beats[i].r, beats[i].pre_rr_s);
            for (int j = 0; j < 4; ++j) printf(" %.6f", beats[i].rr[j]);
            for (int j = 0; j < BEATS_WIN; ++j) printf(" %.5f", beats[i].win[j]);
            printf("\n");
        }
    }
    return 0;
}
