/* Host build of main/edge_rule.c for test_ecg_beats.py (TC-W09). Arguments: window, min_abnormal,
 * cooldown_ms. Each stdin line is one beat, "<cls> <pN> <pS> <pV> <now_ms>", or "clear"; each
 * output line is "A <label> <confidence> <abnormal>" when the beat raises an alert, else "-". */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "edge_rule.h"

int main(int argc, char **argv)
{
    if (argc < 4) return 2;
    edge_rule_t r;
    edge_rule_init(&r, (size_t)atoi(argv[1]), (size_t)atoi(argv[2]), atoll(argv[3]));
    char line[256];
    while (fgets(line, sizeof(line), stdin)) {
        if (!strncmp(line, "clear", 5)) {
            edge_rule_clear(&r);
            printf("-\n");
            continue;
        }
        int cls;
        float p[3];
        long long now;
        if (sscanf(line, "%d %f %f %f %lld", &cls, &p[0], &p[1], &p[2], &now) != 5) return 3;
        edge_alert_t a;
        if (edge_rule_push(&r, cls, p, now, &a)) printf("A %s %.3f %zu\n", a.label, a.confidence, a.abnormal);
        else printf("-\n");
    }
    return 0;
}
