/* Host build of main/alert.c for test_check_capture.py: prints two alerts as mosquitto_sub -v lines. */
#include <stdio.h>
#include <stdlib.h>

#include "alert.h"
#include "cJSON.h"

int main(int argc, char **argv)
{
    const char *device_id = argc > 1 ? argv[1] : "00000000-0000-4000-8000-000000000000";
    for (uint64_t seq = 0; seq < 2; ++seq) {
        char *payload = alert_build(seq);
        if (!payload) return 1;
        printf("mm/fixed/%s/alert %s\n", device_id, payload);
        cJSON_free(payload);
    }
    return 0;
}
