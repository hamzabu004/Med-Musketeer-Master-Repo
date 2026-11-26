set(srcs "../main.c" "display.c" "ui.c" "elog.c" "fixed_path.c" "alert.c" "ecg_convert.c" "ecg_synth.c" "ecg_sampler.c")
if(CONFIG_WEARABLE_ECG_FRONTEND_ADS1292)
    list(APPEND srcs "ecg_ads1292.c")
endif()
if(CONFIG_WEARABLE_EDGE_MODEL)
    list(APPEND srcs "ecg_beats.c" "edge_rule.c" "edge_model.c" "ecg_model/ecg_classifier.cpp")
endif()

idf_component_register(
    SRCS ${srcs}
    INCLUDE_DIRS "." "ecg_model"
    REQUIRES app_update bootloader_support bt driver esp_driver_spi esp_timer esp_driver_gpio esp_driver_i2c esp_hw_support esp_lcd
             esp_netif esp_wifi esp_event mbedtls nvs_flash mqtt qrcode cjson sh1106-esp-idf
             esp-tflite-micro
)
