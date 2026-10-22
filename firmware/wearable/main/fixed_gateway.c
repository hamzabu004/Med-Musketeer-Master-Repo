#include <ctype.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "cJSON.h"
#include "display.h"
#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif_sntp.h"
#include "mqtt_client.h"
#include "mbedtls/oid.h"
#include "mbedtls/x509_crt.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "host/ble_gap.h"
#include "host/ble_gatt.h"
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "os/os_mbuf.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
#include "host/ble_store.h"
#include "store/config/ble_store_config.h"

extern void ble_store_config_init(void);

static const char *TAG = "fixed_gateway";

#define SSID_MAX_LEN 32
#define PASSWORD_MAX_LEN 63
#define BROKER_HOST_MAX_LEN 96
#define CONFIG_JSON_MAX_LEN 512
#define NVS_NAMESPACE "gateway"
#define NVS_KEY_SSID "ssid"
#define NVS_KEY_PASSWORD "password"
#define NVS_KEY_HOST "broker_host"
#define NVS_KEY_PORT "broker_port"
#define CREDS_PARTITION "creds"
#define CREDS_NAMESPACE "creds"
#define CREDS_KEY_PRIVATE "device_key"
#define CREDS_KEY_CERT "device_cert"
#define CREDS_KEY_CA "ca_cert"
#define TLS_PEM_MAX_LEN 4096
#define DEVICE_ID_MAX_LEN 64
#define ALERT_TOPIC_MAX_LEN 96
#define CLOCK_VALID_AFTER 1704067200
#define CLOCK_SYNC_WAIT_MS 10000
#define SNTP_SERVER_COUNT 3

/* UUID: 7a2e0001-2b3c-4d5e-8f90-123456789abc */
static const ble_uuid128_t provisioning_service_uuid = BLE_UUID128_INIT(
    0xbc, 0x9a, 0x78, 0x56, 0x34, 0x12, 0x90, 0x8f,
    0x5e, 0x4d, 0x3c, 0x2b, 0x01, 0x00, 0x2e, 0x7a);
/* UUID: 7a2e0002-2b3c-4d5e-8f90-123456789abc */
static const ble_uuid128_t provisioning_config_uuid = BLE_UUID128_INIT(
    0xbc, 0x9a, 0x78, 0x56, 0x34, 0x12, 0x90, 0x8f,
    0x5e, 0x4d, 0x3c, 0x2b, 0x02, 0x00, 0x2e, 0x7a);

typedef struct {
    char ssid[SSID_MAX_LEN + 1];
    char password[PASSWORD_MAX_LEN + 1];
    char broker_host[BROKER_HOST_MAX_LEN + 1];
    uint16_t broker_port;
} gateway_config_t;

typedef enum {
    NETWORK_REQUEST_APPLY_CONFIG,
    NETWORK_REQUEST_CLEAR_WIFI,
} network_request_type_t;

typedef struct {
    network_request_type_t type;
    gateway_config_t config;
} network_request_t;

static QueueHandle_t config_queue;
static esp_mqtt_client_handle_t mqtt_client;
static SemaphoreHandle_t mqtt_client_mutex;
static char device_name[24];
static char mqtt_uri[160];
static char device_id[DEVICE_ID_MAX_LEN + 1];
static char alert_topic[ALERT_TOPIC_MAX_LEN];
static uint8_t own_addr_type;
static bool wifi_started;
static volatile bool wifi_has_ip;
static volatile bool wifi_configured;
static volatile bool mqtt_connected;
static char tls_device_key[TLS_PEM_MAX_LEN];
static char tls_device_cert[TLS_PEM_MAX_LEN];
static char tls_ca_cert[TLS_PEM_MAX_LEN];
static bool tls_credentials_ready;
static bool sntp_started;
static TaskHandle_t clock_task_handle;

static void network_task(void *arg);
static void start_mqtt_check(const gateway_config_t *config);
static void start_advertising(void);

static bool copy_json_string(const cJSON *root, const char *key, char *out,
                             size_t out_size, bool may_be_empty)
{
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(root, key);
    if (!cJSON_IsString(item) || !item->valuestring) return false;
    size_t length = strlen(item->valuestring);
    if ((!may_be_empty && length == 0) || length >= out_size) return false;
    for (size_t i = 0; i < length; ++i) {
        unsigned char c = (unsigned char)item->valuestring[i];
        if (c < 0x20 || c == 0x7f) return false;
    }
    memcpy(out, item->valuestring, length + 1);
    return true;
}

static bool valid_broker_host(const char *host)
{
    size_t length = strlen(host);
    if (length == 0 || length > BROKER_HOST_MAX_LEN) return false;
    for (size_t i = 0; i < length; ++i) {
        unsigned char c = (unsigned char)host[i];
        if (!(isalnum(c) || c == '.' || c == '-')) return false;
    }
    return true;
}

static bool parse_provisioning_json(const uint8_t *data, size_t length,
                                    network_request_t *request)
{
    if (!length || length >= CONFIG_JSON_MAX_LEN) return false;
    char json[CONFIG_JSON_MAX_LEN];
    memcpy(json, data, length);
    json[length] = '\0';

    cJSON *root = cJSON_ParseWithLength(json, length);
    if (!root || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return false;
    }

    const cJSON *action = cJSON_GetObjectItemCaseSensitive(root, "action");
    if (cJSON_IsString(action) && action->valuestring &&
        strcmp(action->valuestring, "clear_wifi") == 0) {
        request->type = NETWORK_REQUEST_CLEAR_WIFI;
        cJSON_Delete(root);
        return true;
    }

    const cJSON *port = cJSON_GetObjectItemCaseSensitive(root, "broker_port");
    gateway_config_t *config = &request->config;
    bool valid = !action &&
                 copy_json_string(root, "ssid", config->ssid, sizeof(config->ssid), false) &&
                 copy_json_string(root, "password", config->password,
                                  sizeof(config->password), true) &&
                 copy_json_string(root, "broker_host", config->broker_host,
                                  sizeof(config->broker_host), false) &&
                 (strlen(config->password) == 0 || strlen(config->password) >= 8) &&
                 valid_broker_host(config->broker_host) &&
                 cJSON_IsNumber(port) && port->valuedouble >= 1 &&
                 port->valuedouble <= 65535 && port->valuedouble == (double)(uint16_t)port->valuedouble;
    if (valid) {
        config->broker_port = (uint16_t)port->valuedouble;
        request->type = NETWORK_REQUEST_APPLY_CONFIG;
    }
    cJSON_Delete(root);

    return valid;
}

static bool connection_is_authenticated(uint16_t conn_handle)
{
    struct ble_gap_conn_desc desc;
    return ble_gap_conn_find(conn_handle, &desc) == 0 &&
           desc.sec_state.encrypted && desc.sec_state.authenticated;
}

static int config_characteristic_access(uint16_t conn_handle, uint16_t attr_handle,
                                        struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    (void)attr_handle;
    (void)arg;
    if (ctxt->op != BLE_GATT_ACCESS_OP_WRITE_CHR) return BLE_ATT_ERR_UNLIKELY;
    if (!connection_is_authenticated(conn_handle)) return BLE_ATT_ERR_INSUFFICIENT_AUTHEN;

    uint16_t length = OS_MBUF_PKTLEN(ctxt->om);
    if (length == 0 || length >= CONFIG_JSON_MAX_LEN) {
        display_show_text("INVALID SETTINGS", "PAYLOAD SIZE", "", "", "", "");
        return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
    }
    uint8_t payload[CONFIG_JSON_MAX_LEN];
    if (os_mbuf_copydata(ctxt->om, 0, length, payload) != 0) return BLE_ATT_ERR_UNLIKELY;

    network_request_t request = {0};
    if (!parse_provisioning_json(payload, length, &request)) {
        ESP_LOGW(TAG, "Rejected invalid BLE provisioning payload");
        display_show_text("INVALID SETTINGS", "CHECK APP VALUES", "", "", "", "");
        return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
    }

    if (xQueueOverwrite(config_queue, &request) != pdPASS) return BLE_ATT_ERR_UNLIKELY;
    if (request.type == NETWORK_REQUEST_CLEAR_WIFI) {
        display_show_text("WIFI CLEAR REQUEST", "PROCESSING...", "", "", "", "");
    } else {
        display_show_text("SETTINGS RECEIVED", "CONNECTING WIFI", request.config.ssid,
                          "", "", "");
    }
    return 0;
}

static const struct ble_gatt_svc_def gatt_services[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &provisioning_service_uuid.u,
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = &provisioning_config_uuid.u,
                .access_cb = config_characteristic_access,
                .flags = BLE_GATT_CHR_F_WRITE | BLE_GATT_CHR_F_WRITE_ENC |
                         BLE_GATT_CHR_F_WRITE_AUTHEN,
            },
            {0},
        },
    },
    {0},
};

static int gap_event_handler(struct ble_gap_event *event, void *arg)
{
    (void)arg;
    switch (event->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (event->connect.status == 0) {
            display_show_text("PHONE CONNECTED", "PAIRING...", "", "", "", "");
            (void)ble_gap_security_initiate(event->connect.conn_handle);
        } else {
            start_advertising();
        }
        return 0;
    case BLE_GAP_EVENT_DISCONNECT:
        if (strlen(device_name) > 0) {
            char payload[64];
            snprintf(payload, sizeof(payload), "%s|7A2E00012B3C4D5E8F90123456789ABC",
                     device_name);
            esp_qrcode_config_t cfg = ESP_QRCODE_CONFIG_DEFAULT();
            cfg.max_qrcode_version = 4;
            cfg.display_func = display_show_qr;
            ESP_ERROR_CHECK(esp_qrcode_generate(&cfg, payload));
        }
        start_advertising();
        return 0;
    case BLE_GAP_EVENT_PASSKEY_ACTION: {
        struct ble_sm_io io = {0};
        if (event->passkey.params.action == BLE_SM_IOACT_DISP) {
            io.action = BLE_SM_IOACT_DISP;
            io.passkey = esp_random() % 1000000;
            char passkey[7];
            snprintf(passkey, sizeof(passkey), "%06" PRIu32, io.passkey);
            display_show_text("ENTER PASSKEY", "ON YOUR PHONE", "", passkey, "", "");
            ESP_LOGI(TAG, "BLE passkey displayed on OLED");
            return ble_sm_inject_io(event->passkey.conn_handle, &io);
        }
        return BLE_HS_EAPP;
    }
    case BLE_GAP_EVENT_ENC_CHANGE:
        if (event->enc_change.status == 0) {
            display_show_text("PHONE PAIRED", "SEND WIFI DATA", "", "", "", "");
        }
        return 0;
    case BLE_GAP_EVENT_REPEAT_PAIRING: {
        struct ble_gap_conn_desc desc;
        if (ble_gap_conn_find(event->repeat_pairing.conn_handle, &desc) == 0) {
            ble_store_util_delete_peer(&desc.peer_id_addr);
        }
        return BLE_GAP_REPEAT_PAIRING_RETRY;
    }
    default:
        return 0;
    }
}

static void advertise_sync(void)
{
    int rc = ble_hs_id_infer_auto(0, &own_addr_type);
    if (rc != 0) {
        ESP_LOGE(TAG, "Unable to infer BLE address type: %d", rc);
        return;
    }
    start_advertising();
}

static void start_advertising(void)
{
    struct ble_hs_adv_fields fields = {0};
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.uuids128 = (ble_uuid128_t *)&provisioning_service_uuid;
    fields.num_uuids128 = 1;
    fields.uuids128_is_complete = 1;

    int rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) {
        ESP_LOGE(TAG, "Unable to set BLE advertising data: %d", rc);
        return;
    }
    struct ble_hs_adv_fields scan_response = {0};
    scan_response.name = (const uint8_t *)device_name;
    scan_response.name_len = strlen(device_name);
    scan_response.name_is_complete = 1;
    rc = ble_gap_adv_rsp_set_fields(&scan_response);
    if (rc != 0) {
        ESP_LOGE(TAG, "Unable to set BLE scan response data: %d", rc);
        return;
    }
    struct ble_gap_adv_params params = {0};
    params.conn_mode = BLE_GAP_CONN_MODE_UND;
    params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    rc = ble_gap_adv_start(own_addr_type, NULL, BLE_HS_FOREVER, &params,
                           gap_event_handler, NULL);
    if (rc != 0 && rc != BLE_HS_EALREADY) {
        ESP_LOGE(TAG, "Unable to start BLE advertising: %d", rc);
    }
}

static void nimble_host_task(void *arg)
{
    (void)arg;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

static void start_ble_provisioning(void)
{
    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_read_mac(mac, ESP_MAC_WIFI_STA));
    snprintf(device_name, sizeof(device_name), "MM-GW-%02X%02X%02X",
             mac[3], mac[4], mac[5]);

    char qr_payload[64];
    snprintf(qr_payload, sizeof(qr_payload), "%s|7A2E00012B3C4D5E8F90123456789ABC",
             device_name);
    esp_qrcode_config_t qr_config = ESP_QRCODE_CONFIG_DEFAULT();
    qr_config.max_qrcode_version = 4;
    qr_config.qrcode_ecc_level = ESP_QRCODE_ECC_LOW;
    qr_config.display_func = display_show_qr;
    ESP_ERROR_CHECK(esp_qrcode_generate(&qr_config, qr_payload));

    ESP_ERROR_CHECK(nimble_port_init());
    ble_hs_cfg.reset_cb = NULL;
    ble_hs_cfg.sync_cb = advertise_sync;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;
    ble_hs_cfg.sm_io_cap = BLE_SM_IO_CAP_DISP_ONLY;
    ble_hs_cfg.sm_bonding = 1;
    ble_hs_cfg.sm_mitm = 1;
    ble_hs_cfg.sm_sc = 1;
    ble_hs_cfg.sm_our_key_dist = BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID;
    ble_hs_cfg.sm_their_key_dist = BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID;

    ble_svc_gap_init();
    ESP_ERROR_CHECK(ble_svc_gap_device_name_set(device_name));
    ble_svc_gatt_init();
    ESP_ERROR_CHECK(ble_gatts_count_cfg(gatt_services));
    ESP_ERROR_CHECK(ble_gatts_add_svcs(gatt_services));
    ble_store_config_init();
    nimble_port_freertos_init(nimble_host_task);
    ESP_LOGI(TAG, "BLE provisioning active: %s", device_name);
}

static bool load_saved_config(gateway_config_t *config)
{
    nvs_handle_t nvs;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) != ESP_OK) return false;

    size_t ssid_len = sizeof(config->ssid);
    size_t password_len = sizeof(config->password);
    size_t host_len = sizeof(config->broker_host);
    uint16_t port = 0;
    esp_err_t err = nvs_get_str(nvs, NVS_KEY_SSID, config->ssid, &ssid_len);
    if (err == ESP_OK) err = nvs_get_str(nvs, NVS_KEY_PASSWORD, config->password, &password_len);
    if (err == ESP_OK) err = nvs_get_str(nvs, NVS_KEY_HOST, config->broker_host, &host_len);
    if (err == ESP_OK) err = nvs_get_u16(nvs, NVS_KEY_PORT, &port);
    nvs_close(nvs);
    if (err != ESP_OK || port == 0 || !valid_broker_host(config->broker_host)) return false;
    config->broker_port = port;
    return config->ssid[0] != '\0';
}

static bool load_device_id_from_certificate(void)
{
    mbedtls_x509_crt cert;
    mbedtls_x509_crt_init(&cert);
    int ret = mbedtls_x509_crt_parse(&cert, (const unsigned char *)tls_device_cert,
                                     strlen(tls_device_cert) + 1);
    if (ret != 0) {
        ESP_LOGE(TAG, "Cannot parse device certificate for MQTT topic identity: -0x%04X",
                 (unsigned)-ret);
        mbedtls_x509_crt_free(&cert);
        return false;
    }

    bool found = false;
    for (const mbedtls_x509_name *name = &cert.subject; name; name = name->next) {
        if (name->oid.len != MBEDTLS_OID_SIZE(MBEDTLS_OID_AT_CN) ||
            memcmp(name->oid.p, MBEDTLS_OID_AT_CN, name->oid.len) != 0 ||
            name->val.len == 0 || name->val.len > DEVICE_ID_MAX_LEN) {
            continue;
        }

        bool safe_topic_id = true;
        for (size_t i = 0; i < name->val.len; ++i) {
            unsigned char c = name->val.p[i];
            if (!(isalnum(c) || c == '-' || c == '_' || c == '.')) {
                safe_topic_id = false;
                break;
            }
        }
        if (!safe_topic_id) continue;

        memcpy(device_id, name->val.p, name->val.len);
        device_id[name->val.len] = '\0';
        found = true;
        break;
    }
    mbedtls_x509_crt_free(&cert);

    if (!found) {
        ESP_LOGE(TAG, "Device certificate has no usable common name for the alert topic");
        return false;
    }

    int topic_len = snprintf(alert_topic, sizeof(alert_topic), "mm/fixed/%s/alert", device_id);
    if (topic_len < 0 || (size_t)topic_len >= sizeof(alert_topic)) {
        device_id[0] = '\0';
        alert_topic[0] = '\0';
        ESP_LOGE(TAG, "Device certificate common name is too long for the alert topic");
        return false;
    }
    ESP_LOGI(TAG, "Periodic alert topic: %s", alert_topic);
    return true;
}

static bool load_tls_credentials(void)
{
    esp_err_t err = nvs_flash_init_partition(CREDS_PARTITION);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Cannot initialize creds partition: %s; reflash credentials",
                 esp_err_to_name(err));
        return false;
    }

    nvs_handle_t nvs;
    err = nvs_open_from_partition(CREDS_PARTITION, CREDS_NAMESPACE, NVS_READONLY, &nvs);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "No credentials namespace in creds partition: %s", esp_err_to_name(err));
        return false;
    }
    size_t key_len = sizeof(tls_device_key);
    size_t cert_len = sizeof(tls_device_cert);
    size_t ca_len = sizeof(tls_ca_cert);
    err = nvs_get_str(nvs, CREDS_KEY_PRIVATE, tls_device_key, &key_len);
    if (err == ESP_OK) err = nvs_get_str(nvs, CREDS_KEY_CERT, tls_device_cert, &cert_len);
    if (err == ESP_OK) err = nvs_get_str(nvs, CREDS_KEY_CA, tls_ca_cert, &ca_len);
    nvs_close(nvs);
    if (err != ESP_OK || key_len <= 1 || cert_len <= 1 || ca_len <= 1) {
        ESP_LOGE(TAG, "Credentials are incomplete or exceed the firmware buffer limit");
        return false;
    }
    if (!load_device_id_from_certificate()) {
        ESP_LOGW(TAG, "MQTT can connect, but periodic alerts are disabled without a usable certificate CN");
    }
    tls_credentials_ready = true;
    ESP_LOGI(TAG, "Loaded TLS credentials from the read-only creds partition");
    return true;
}

static esp_err_t save_config(const gateway_config_t *config)
{
    nvs_handle_t nvs;
    ESP_RETURN_ON_ERROR(nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs), TAG,
                        "cannot open NVS configuration");
    esp_err_t err = nvs_set_str(nvs, NVS_KEY_SSID, config->ssid);
    if (err == ESP_OK) err = nvs_set_str(nvs, NVS_KEY_PASSWORD, config->password);
    if (err == ESP_OK) err = nvs_set_str(nvs, NVS_KEY_HOST, config->broker_host);
    if (err == ESP_OK) err = nvs_set_u16(nvs, NVS_KEY_PORT, config->broker_port);
    if (err == ESP_OK) err = nvs_commit(nvs);
    nvs_close(nvs);
    return err;
}

static esp_err_t clear_saved_wifi_credentials(void)
{
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err == ESP_ERR_NVS_NOT_FOUND) return ESP_OK;
    ESP_RETURN_ON_ERROR(err, TAG, "cannot open NVS configuration");
    err = nvs_erase_key(nvs, NVS_KEY_SSID);
    if (err == ESP_ERR_NVS_NOT_FOUND) err = ESP_OK;
    if (err == ESP_OK) {
        err = nvs_erase_key(nvs, NVS_KEY_PASSWORD);
        if (err == ESP_ERR_NVS_NOT_FOUND) err = ESP_OK;
    }
    if (err == ESP_OK) err = nvs_commit(nvs);
    nvs_close(nvs);
    return err;
}

static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    (void)handler_args;
    (void)base;
    (void)event_data;
    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        mqtt_connected = true;
        ESP_LOGI(TAG, "MQTT broker accepted CONNECT (CONNACK received)");
        if (wifi_has_ip) display_show_text("WIFI CONNECTED", "MQTT REACHABLE", "", "", "", "");
        break;
    case MQTT_EVENT_ERROR:
        mqtt_connected = false;
        if (!wifi_has_ip) break;
        ESP_LOGW(TAG, "MQTT broker connection failed");
        display_show_text("WIFI CONNECTED", "MQTT CHECK FAILED", "RETRYING...", "", "", "");
        break;
    case MQTT_EVENT_DISCONNECTED:
        mqtt_connected = false;
        if (wifi_has_ip) display_show_text("WIFI CONNECTED", "MQTT DISCONNECTED", "RETRYING...", "", "", "");
        break;
    default:
        break;
    }
}

static void alert_publish_task(void *arg)
{
    (void)arg;
    for (;;) {
        if (!mqtt_connected || !wifi_has_ip || !device_id[0] || !alert_topic[0]) {
            vTaskDelay(pdMS_TO_TICKS(250));
            continue;
        }

        uint32_t delay_ms = 2000U + (esp_random() % 3001U);
        vTaskDelay(pdMS_TO_TICKS(delay_ms));
        if (!mqtt_connected || !wifi_has_ip || !device_id[0] || !alert_topic[0]) continue;

        cJSON *alert = cJSON_CreateObject();
        if (!alert ||
            !cJSON_AddStringToObject(alert, "device_id", device_id) ||
            !cJSON_AddStringToObject(alert, "type", "test_alert") ||
            !cJSON_AddStringToObject(alert, "message", "Periodic ESP32 test alert") ||
            !cJSON_AddNumberToObject(alert, "timestamp", (double)time(NULL))) {
            ESP_LOGE(TAG, "Cannot build alert JSON payload");
            cJSON_Delete(alert);
            continue;
        }

        char *payload = cJSON_PrintUnformatted(alert);
        cJSON_Delete(alert);
        if (!payload) {
            ESP_LOGE(TAG, "Cannot serialize alert JSON payload");
            continue;
        }

        if (xSemaphoreTake(mqtt_client_mutex, portMAX_DELAY) == pdTRUE) {
            if (mqtt_connected && wifi_has_ip && mqtt_client) {
                int message_id = esp_mqtt_client_publish(mqtt_client, alert_topic,
                                                         payload, 0, 1, 0);
                if (message_id >= 0) {
                    ESP_LOGI(TAG, "Published alert to %s (message id %d)",
                             alert_topic, message_id);
                } else {
                    ESP_LOGW(TAG, "Failed to queue alert publish to %s", alert_topic);
                }
            }
            xSemaphoreGive(mqtt_client_mutex);
        }
        cJSON_free(payload);
    }
}

/* Waits outside the event loop until SNTP sets the clock, then starts MQTT. SNTP keeps
 * retrying and moves to the next server on timeout, so one dead server no longer blocks TLS. */
static void clock_sync_task(void *arg)
{
    (void)arg;
    while (time(NULL) < CLOCK_VALID_AFTER) {
        if (esp_netif_sntp_sync_wait(pdMS_TO_TICKS(CLOCK_SYNC_WAIT_MS)) != ESP_OK &&
            time(NULL) < CLOCK_VALID_AFTER) {
            ESP_LOGW(TAG, "System clock not synchronized yet; SNTP is retrying");
        }
    }
    ESP_LOGI(TAG, "System clock synchronized");
    clock_task_handle = NULL;
    gateway_config_t config;
    if (wifi_has_ip && wifi_configured && load_saved_config(&config)) start_mqtt_check(&config);
    vTaskDelete(NULL);
}

static void start_mqtt_check(const gateway_config_t *config)
{
    if (!tls_credentials_ready) {
        display_show_text("WIFI CONNECTED", "TLS CREDS MISSING", "FLASH DEVICE IDENTITY", "", "", "");
        return;
    }
    if (time(NULL) < CLOCK_VALID_AFTER) {
        if (!sntp_started) {
            const esp_sntp_config_t sntp_config = ESP_NETIF_SNTP_DEFAULT_CONFIG_MULTIPLE(
                SNTP_SERVER_COUNT,
                ESP_SNTP_SERVER_LIST("time.google.com", "pool.ntp.org", "time.cloudflare.com"));
            esp_err_t err = esp_netif_sntp_init(&sntp_config);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Cannot start SNTP before TLS validation: %s", esp_err_to_name(err));
                display_show_text("WIFI CONNECTED", "CLOCK SYNC FAILED", "TLS NOT STARTED", "", "", "");
                return;
            }
            sntp_started = true;
        }
        display_show_text("WIFI CONNECTED", "SYNCING CLOCK...", "TLS WAITS FOR TIME", "", "", "");
        if (!clock_task_handle &&
            xTaskCreate(clock_sync_task, "gateway_clock", 4096, NULL, 4, &clock_task_handle) != pdPASS) {
            clock_task_handle = NULL;
            ESP_LOGE(TAG, "Cannot start the clock sync task; refusing TLS connection");
            display_show_text("WIFI CONNECTED", "CLOCK SYNC FAILED", "TLS NOT STARTED", "", "", "");
        }
        return;
    }
    bool start_client = false;
    xSemaphoreTake(mqtt_client_mutex, portMAX_DELAY);
    if (!mqtt_client) {
        snprintf(mqtt_uri, sizeof(mqtt_uri), "mqtts://%s:%u", config->broker_host,
                 (unsigned)config->broker_port);
        const esp_mqtt_client_config_t mqtt_config = {
            .broker.address.uri = mqtt_uri,
            .broker.verification.certificate = tls_ca_cert,
            .broker.verification.certificate_len = strlen(tls_ca_cert) + 1,
            .broker.verification.common_name = "gateway.medmusketeer.local",
            .broker.verification.skip_cert_common_name_check = false,
            .credentials.authentication.certificate = tls_device_cert,
            .credentials.authentication.certificate_len = strlen(tls_device_cert) + 1,
            .credentials.authentication.key = tls_device_key,
            .credentials.authentication.key_len = strlen(tls_device_key) + 1,
            .session.keepalive = 20,
            .network.timeout_ms = 5000,
        };
        mqtt_client = esp_mqtt_client_init(&mqtt_config);
        if (!mqtt_client) {
            xSemaphoreGive(mqtt_client_mutex);
            display_show_text("WIFI CONNECTED", "MQTT INIT FAILED", "", "", "", "");
            return;
        }
        ESP_ERROR_CHECK(esp_mqtt_client_register_event(mqtt_client, ESP_EVENT_ANY_ID,
                                                        mqtt_event_handler, NULL));
        start_client = true;
    }
    display_show_text("WIFI CONNECTED", "CHECKING MQTT...", "", "", "", "");
    if (start_client) ESP_ERROR_CHECK(esp_mqtt_client_start(mqtt_client));
    xSemaphoreGive(mqtt_client_mutex);
}

static void wifi_event_handler(void *arg, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    (void)arg;
    if (base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        if (wifi_configured) ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_has_ip = false;
        mqtt_connected = false;
        if (wifi_configured) {
            display_show_text("WIFI DISCONNECTED", "RETRYING...", "", "", "", "");
            (void)esp_wifi_connect();
        }
    } else if (base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        wifi_has_ip = true;
        if (wifi_configured) {
            gateway_config_t config;
            if (load_saved_config(&config)) start_mqtt_check(&config);
        }
    }
}

static void apply_config(const gateway_config_t *config, bool persist)
{
    if (persist) {
        esp_err_t err = save_config(config);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Unable to save provisioning settings: %s", esp_err_to_name(err));
            display_show_text("NVS SAVE FAILED", "CHECK FLASH", "", "", "", "");
            return;
        }
    }
    xSemaphoreTake(mqtt_client_mutex, portMAX_DELAY);
    mqtt_connected = false;
    if (mqtt_client) {
        esp_mqtt_client_stop(mqtt_client);
        esp_mqtt_client_destroy(mqtt_client);
        mqtt_client = NULL;
    }
    xSemaphoreGive(mqtt_client_mutex);
    if (wifi_started) (void)esp_wifi_disconnect();
    wifi_configured = true;

    wifi_config_t wifi_config = {0};
    strlcpy((char *)wifi_config.sta.ssid, config->ssid, sizeof(wifi_config.sta.ssid));
    strlcpy((char *)wifi_config.sta.password, config->password,
            sizeof(wifi_config.sta.password));
    wifi_config.sta.threshold.authmode = WIFI_AUTH_OPEN;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    if (!wifi_started) {
        ESP_ERROR_CHECK(esp_wifi_start());
        wifi_started = true;
    } else {
        (void)esp_wifi_connect();
    }
}

static void clear_wifi_credentials(void)
{
    wifi_configured = false;
    wifi_has_ip = false;
    xSemaphoreTake(mqtt_client_mutex, portMAX_DELAY);
    mqtt_connected = false;
    if (mqtt_client) {
        (void)esp_mqtt_client_stop(mqtt_client);
        esp_mqtt_client_destroy(mqtt_client);
        mqtt_client = NULL;
    }
    xSemaphoreGive(mqtt_client_mutex);
    if (wifi_started) {
        (void)esp_wifi_disconnect();
        (void)esp_wifi_stop();
        wifi_started = false;
    }

    esp_err_t err = clear_saved_wifi_credentials();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Unable to clear saved Wi-Fi credentials: %s", esp_err_to_name(err));
        display_show_text("WIFI CLEAR FAILED", "NVS ERROR", "", "", "", "");
        return;
    }

    /* Older firmware may also have persisted the station config in Wi-Fi NVS. */
    err = esp_wifi_set_storage(WIFI_STORAGE_FLASH);
    if (err == ESP_OK) err = esp_wifi_restore();
    if (err == ESP_OK) err = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (err == ESP_OK) err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Unable to clear Wi-Fi driver settings: %s", esp_err_to_name(err));
        display_show_text("WIFI CLEAR FAILED", "WIFI RESET ERROR", "APP KEYS CLEARED", "", "", "");
        return;
    }

    display_show_text("WIFI CREDENTIALS", "CLEARED", "BROKER AND TLS KEPT", "", "", "");
    ESP_LOGI(TAG, "Cleared Wi-Fi SSID/password; broker settings and TLS credentials were kept");
}

static void network_task(void *arg)
{
    (void)arg;
    network_request_t request;
    for (;;) {
        if (xQueueReceive(config_queue, &request, portMAX_DELAY) == pdTRUE) {
            if (request.type == NETWORK_REQUEST_CLEAR_WIFI) clear_wifi_credentials();
            else apply_config(&request.config, true);
        }
    }
}

void fixed_gateway_start(void)
{
    tls_credentials_ready = load_tls_credentials();
    mqtt_client_mutex = xSemaphoreCreateMutex();
    ESP_ERROR_CHECK(mqtt_client_mutex ? ESP_OK : ESP_ERR_NO_MEM);
    ESP_ERROR_CHECK(xTaskCreate(alert_publish_task, "gateway_alerts", 4096,
                                NULL, 4, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM);
    config_queue = xQueueCreate(1, sizeof(network_request_t));
    ESP_ERROR_CHECK(config_queue ? ESP_OK : ESP_ERR_NO_MEM);
    xTaskCreate(network_task, "gateway_network", 6144, NULL, 5, NULL);

    esp_netif_create_default_wifi_sta();
    wifi_init_config_t wifi_init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_init));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                                wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                                wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));

    start_ble_provisioning();

    gateway_config_t saved_config = {0};
    if (load_saved_config(&saved_config)) {
        ESP_LOGI(TAG, "Using saved Wi-Fi provisioning");
        apply_config(&saved_config, false);
    } else {
        ESP_LOGI(TAG, "Waiting for BLE Wi-Fi provisioning");
    }
}
