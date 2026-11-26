#include <stdlib.h>
#include <time.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "nvs_flash.h"

#include "display.h"
#include "ecg_sampler.h"
#include "edge_model.h"
#include "elog.h"
#include "ui.h"

#if CONFIG_WEARABLE_MODE_FIXED
#include "fixed_path.h"
#endif

static const char *TAG = "wearable_app";

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    /* Local time for the OLED's log page. */
    setenv("TZ", CONFIG_WEARABLE_TIMEZONE, 1);
    tzset();
    elog_add("BOOT");
    ESP_ERROR_CHECK(display_init());
    ESP_ERROR_CHECK(ui_start());
    /* Always on (Iteration 5, D-3), and the on-device model on top of it. A front-end or model
     * failure leaves ECG or the model off, not the wearable. */
    if (ecg_sampler_start() == ESP_OK) (void)edge_model_start();

#if CONFIG_WEARABLE_MODE_FIXED
    ESP_LOGI(TAG, "Fixed path build");
    fixed_path_start();
#else
    ESP_LOGI(TAG, "Mobile mode firmware is not implemented yet");
    display_show_text("MOBILE MODE", "NOT IMPLEMENTED", "", "", "", "");
#endif
}
