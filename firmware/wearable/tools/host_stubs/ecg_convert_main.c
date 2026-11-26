/* Host build of main/ecg_convert.c for test_ecg_convert.py (TC-W07). Reads commands on stdin and
 * prints one result per line:
 *   frame <18 hex digits>     "<ok> <status hex> <ch1> <ch2> <leads_off>"
 *   uv <code>...              microvolts at the default reference and gain, 6 decimals
 *   counts <cpm> <uv>...      int16 counts
 *   hp <fc> <fs> <x>...       the DC blocker's outputs, 3 decimals
 *   lo <flag>...              the leads-off count */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ecg_convert.h"

int main(void)
{
    static char line[1 << 20];
    while (fgets(line, sizeof(line), stdin)) {
        char *tok = strtok(line, " \n");
        if (!tok) continue;
        if (!strcmp(tok, "frame")) {
            const char *hex = strtok(NULL, " \n");
            uint8_t raw[ADS1292_FRAME_BYTES];
            for (int i = 0; i < ADS1292_FRAME_BYTES; ++i) {
                char byte[3] = {hex[2 * i], hex[2 * i + 1], 0};
                raw[i] = (uint8_t)strtoul(byte, NULL, 16);
            }
            ads1292_frame_t f;
            const bool ok = ads1292_parse_frame(raw, &f);
            printf("%d %06x %d %d %u", ok, (unsigned)f.status, (int)f.ch1, (int)f.ch2,
                   ads1292_ch1_leads_off(f.status));
        } else if (!strcmp(tok, "uv")) {
            while ((tok = strtok(NULL, " \n"))) {
                printf("%.6f ", ads1292_code_to_uv(atoi(tok), ADS1292_VREF_UV, ADS1292_GAIN));
            }
        } else if (!strcmp(tok, "counts")) {
            const int cpm = atoi(strtok(NULL, " \n"));
            while ((tok = strtok(NULL, " \n"))) printf("%d ", ecg_uv_to_counts((float)atof(tok), cpm));
        } else if (!strcmp(tok, "hp")) {
            ecg_dc_block_t f;
            const float fc = (float)atof(strtok(NULL, " \n"));
            const float fs = (float)atof(strtok(NULL, " \n"));
            ecg_dc_block_init(&f, fc, fs);
            while ((tok = strtok(NULL, " \n"))) printf("%.3f ", ecg_dc_block(&f, (float)atof(tok)));
        } else if (!strcmp(tok, "lo")) {
            uint8_t flags[1024];
            size_t n = 0;
            while ((tok = strtok(NULL, " \n")) && n < sizeof(flags)) flags[n++] = (uint8_t)atoi(tok);
            printf("%zu", ecg_count_leads_off(flags, n));
        }
        printf("\n");
    }
    return 0;
}
