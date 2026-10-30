package com.example.qr

import com.example.ble.BleConstants
import com.example.model.GatewayQrResult
import java.util.Locale

object QrParser {

    /**
     * Parses and validates raw QR payload text from wearable OLED.
     * Expected format: MM-WR-XXXXXX|7A2E00012B3C4D5E8F90123456789ABC
     */
    fun parse(rawText: String?): GatewayQrResult {
        if (rawText.isNullOrBlank()) {
            return GatewayQrResult(
                rawText = "",
                isValid = false,
                errorMessage = "QR code payload is empty"
            )
        }

        val trimmed = rawText.trim()
        val parts = trimmed.split("|")
        if (parts.size != 2) {
            return GatewayQrResult(
                rawText = trimmed,
                isValid = false,
                errorMessage = "Invalid QR structure: expected exactly 2 fields separated by '|' (got ${parts.size})"
            )
        }

        val deviceNameRaw = parts[0].trim().uppercase(Locale.ROOT)
        val serviceUuidRaw = parts[1].trim().replace("-", "").uppercase(Locale.ROOT)

        // Validate device name
        if (!BleConstants.DEVICE_NAME_REGEX.matches(deviceNameRaw)) {
            return GatewayQrResult(
                rawText = trimmed,
                deviceName = deviceNameRaw,
                serviceUuidHex = serviceUuidRaw,
                isValid = false,
                errorMessage = "Invalid wearable name '$deviceNameRaw': must follow 'MM-WR-XXXXXX' format with 6 hex characters"
            )
        }

        // Validate service UUID (case-insensitive comparison with expected service UUID hex)
        val expectedUuidHex = BleConstants.SERVICE_UUID_RAW_HEX.uppercase(Locale.ROOT)
        if (serviceUuidRaw != expectedUuidHex) {
            return GatewayQrResult(
                rawText = trimmed,
                deviceName = deviceNameRaw,
                serviceUuidHex = serviceUuidRaw,
                isValid = false,
                errorMessage = "Unrecognized service UUID '$serviceUuidRaw'. Expected MedMusketeer service UUID"
            )
        }

        return GatewayQrResult(
            rawText = trimmed,
            deviceName = deviceNameRaw,
            serviceUuidHex = serviceUuidRaw,
            isValid = true,
            errorMessage = null
        )
    }

    /**
     * Validates a manually entered device name (e.g. MM-WR-A1B2C3).
     */
    fun validateDeviceName(input: String?): Result<String> {
        if (input.isNullOrBlank()) {
            return Result.failure(IllegalArgumentException("Wearable name cannot be empty"))
        }
        val normalized = input.trim().uppercase(Locale.ROOT)
        return if (BleConstants.DEVICE_NAME_REGEX.matches(normalized)) {
            Result.success(normalized)
        } else {
            Result.failure(IllegalArgumentException("Wearable name must be 'MM-WR-' followed by 6 hex characters (e.g. MM-WR-A1B2C3)"))
        }
    }
}
