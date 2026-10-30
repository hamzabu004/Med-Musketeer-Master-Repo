idf_component_register(
    SRCS "../main.c" "display.c" "fixed_path.c" "alert.c"
    INCLUDE_DIRS "."
    REQUIRES bt driver esp_driver_gpio esp_driver_i2c esp_hw_support esp_lcd esp_netif esp_wifi esp_event
             mbedtls nvs_flash mqtt qrcode cjson sh1106-esp-idf
)
