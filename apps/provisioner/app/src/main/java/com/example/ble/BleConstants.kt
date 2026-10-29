package com.example.ble

import java.util.UUID

object BleConstants {
    // Provisioning Service UUID: 7a2e0001-2b3c-4d5e-8f90-123456789abc
    val SERVICE_UUID: UUID = UUID.fromString("7a2e0001-2b3c-4d5e-8f90-123456789abc")

    // Raw 32-character hex representation from QR code
    const val SERVICE_UUID_RAW_HEX = "7A2E00012B3C4D5E8F90123456789ABC"

    // Provisioning Configuration Characteristic UUID: 7a2e0002-2b3c-4d5e-8f90-123456789abc
    val CONFIG_CHAR_UUID: UUID = UUID.fromString("7a2e0002-2b3c-4d5e-8f90-123456789abc")

    // Target device name format: MM-WR-XXXXXX (where XXXXXX is 6 hex characters)
    val DEVICE_NAME_REGEX = Regex("^MM-WR-[0-9A-Fa-f]{6}$")

    // MQTT Broker Host format: 1 to 96 ASCII letters, digits, dots, hyphens
    val BROKER_HOST_REGEX = Regex("^[a-zA-Z0-9.-]{1,96}$")

    // MTU requested during connection setup
    const val REQUESTED_MTU = 517

    // Maximum payload bytes allowed by firmware (rejects >= 512 bytes)
    const val MAX_PAYLOAD_BYTES = 511

    // Scan timeout in milliseconds
    const val SCAN_TIMEOUT_MS = 15000L

    // Connection timeout in milliseconds
    const val CONNECTION_TIMEOUT_MS = 20000L

    // GATT write timeout in milliseconds
    const val WRITE_TIMEOUT_MS = 15000L
}
