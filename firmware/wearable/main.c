#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "nvs_flash.h"

#include "display.h"

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
    ESP_ERROR_CHECK(display_init());

#if CONFIG_WEARABLE_MODE_FIXED
    ESP_LOGI(TAG, "Fixed path build");
    fixed_path_start();
#else
    ESP_LOGI(TAG, "Mobile mode firmware is not implemented yet");
    display_show_text("MOBILE MODE", "NOT IMPLEMENTED", "", "", "", "");
#endif
}
