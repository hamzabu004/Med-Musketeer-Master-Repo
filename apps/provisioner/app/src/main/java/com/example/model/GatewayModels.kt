package com.example.model

import android.bluetooth.BluetoothDevice
import com.example.ble.BleConstants
import org.json.JSONObject

/**
 * Represents a discovered MedMusketeer BLE wearable device.
 */
data class GatewayDevice(
    val name: String,
    val address: String,
    val rssi: Int,
    val bluetoothDevice: BluetoothDevice? = null,
    val lastSeenTimestamp: Long = System.currentTimeMillis()
)

/**
 * Result of parsing and validating an OLED QR code string.
 */
data class GatewayQrResult(
    val rawText: String,
    val deviceName: String = "",
    val serviceUuidHex: String = "",
    val isValid: Boolean = false,
    val errorMessage: String? = null
)

/**
 * Configuration payload for the wearable provisioning write.
 */
data class ProvisioningConfig(
    val ssid: String = "",
    val password: String = "",
    val isOpenWifi: Boolean = false,
    val brokerHost: String = "",
    val brokerPort: Int = 1883
) {
    /**
     * Validates fields according to ESP32 firmware constraints.
     * Returns null if valid, or a descriptive error message if invalid.
     */
    fun validate(): ValidationResult {
        val trimmedSsid = ssid.trim()
        if (trimmedSsid.isEmpty()) {
            return ValidationResult(isValid = false, field = "ssid", error = "Wi-Fi SSID is required")
        }
        if (trimmedSsid.length > 32) {
            return ValidationResult(isValid = false, field = "ssid", error = "SSID must be 1 to 32 characters (current: ${trimmedSsid.length})")
        }

        if (!isOpenWifi) {
            if (password.length < 8 || password.length > 63) {
                return ValidationResult(
                    isValid = false,
                    field = "password",
                    error = "Password must be 8 to 63 characters for secured networks (current: ${password.length})"
                )
            }
        }

        val trimmedHost = brokerHost.trim()
        if (trimmedHost.isEmpty()) {
            return ValidationResult(isValid = false, field = "brokerHost", error = "MQTT Broker host is required")
        }
        if (trimmedHost.length > 96) {
            return ValidationResult(isValid = false, field = "brokerHost", error = "Broker host cannot exceed 96 characters (current: ${trimmedHost.length})")
        }
        if (!BleConstants.BROKER_HOST_REGEX.matches(trimmedHost)) {
            return ValidationResult(
                isValid = false,
                field = "brokerHost",
                error = "Broker host can only contain ASCII letters, digits, dots, and hyphens (IPv6 not supported)"
            )
        }

        if (brokerPort < 1 || brokerPort > 65535) {
            return ValidationResult(isValid = false, field = "brokerPort", error = "MQTT Broker port must be an integer between 1 and 65535")
        }

        val json = toJsonPayload()
        val byteCount = json.toByteArray(Charsets.UTF_8).size
        if (byteCount > BleConstants.MAX_PAYLOAD_BYTES) {
            return ValidationResult(
                isValid = false,
                field = "payload",
                error = "Total JSON payload exceeds firmware limit ($byteCount bytes, max ${BleConstants.MAX_PAYLOAD_BYTES})"
            )
        }

        return ValidationResult(isValid = true, byteCount = byteCount)
    }

    /**
     * Serializes to exact JSON format required by ESP32-S3 firmware:
     * {"ssid":"...","password":"...","broker_host":"...","broker_port":1883}
     */
    fun toJsonPayload(): String {
        val json = JSONObject()
        json.put("ssid", ssid.trim())
        json.put("password", if (isOpenWifi) "" else password)
        json.put("broker_host", brokerHost.trim())
        json.put("broker_port", brokerPort)
        return json.toString()
    }

    fun payloadSizeBytes(): Int {
        return toJsonPayload().toByteArray(Charsets.UTF_8).size
    }
}

data class ValidationResult(
    val isValid: Boolean,
    val field: String? = null,
    val error: String? = null,
    val byteCount: Int = 0
)

/**
 * Steps in the connection and provisioning lifecycle.
 */
enum class ConnectionStage {
    IDLE,
    SCANNING,
    DEVICE_FOUND,
    CONNECTING_GATT,
    REQUESTING_MTU,
    DISCOVERING_SERVICES,
    WAITING_FOR_BONDING,
    BONDED,
    WRITING_CONFIG,
    WRITE_SUCCESS,
    FAILED
}

/**
 * Screen routing destinations.
 */
enum class SetupScreen {
    WELCOME,
    SCAN_QR,
    DISCOVERY,
    PAIRING,
    CONFIG_FORM,
    REVIEW_SEND,
    RESULT
}
