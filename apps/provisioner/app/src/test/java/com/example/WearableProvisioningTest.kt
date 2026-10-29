package com.example

import com.example.ble.BleConstants
import com.example.model.ProvisioningConfig
import com.example.qr.QrParser
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class WearableProvisioningTest {

    @Test
    fun testValidQrParsing() {
        val raw = "MM-WR-A1B2C3|7A2E00012B3C4D5E8F90123456789ABC"
        val result = QrParser.parse(raw)

        assertTrue("Expected valid QR result", result.isValid)
        assertEquals("MM-WR-A1B2C3", result.deviceName)
        assertEquals("7A2E00012B3C4D5E8F90123456789ABC", result.serviceUuidHex)
    }

    @Test
    fun testCaseInsensitiveQrParsing() {
        val raw = "mm-wr-1234ef|7a2e00012b3c4d5e8f90123456789abc"
        val result = QrParser.parse(raw)

        assertTrue("Expected case-insensitive QR to parse as valid", result.isValid)
        assertEquals("MM-WR-1234EF", result.deviceName)
        assertEquals("7A2E00012B3C4D5E8F90123456789ABC", result.serviceUuidHex)
    }

    @Test
    fun testMalformedQrWithoutPipe() {
        val raw = "MM-WR-A1B2C37A2E00012B3C4D5E8F90123456789ABC"
        val result = QrParser.parse(raw)

        assertFalse(result.isValid)
        assertNotNull(result.errorMessage)
    }

    @Test
    fun testInvalidDeviceNameInQr() {
        // Only 5 hex characters
        val raw = "MM-WR-12345|7A2E00012B3C4D5E8F90123456789ABC"
        val result = QrParser.parse(raw)

        assertFalse(result.isValid)
        assertTrue(result.errorMessage?.contains("Invalid wearable name") == true)
    }

    @Test
    fun testInvalidServiceUuidInQr() {
        // Wrong service UUID
        val raw = "MM-WR-A1B2C3|00000000000000000000000000000000"
        val result = QrParser.parse(raw)

        assertFalse(result.isValid)
        assertTrue(result.errorMessage?.contains("Unrecognized service UUID") == true)
    }

    @Test
    fun testManualDeviceNameValidation() {
        assertTrue(QrParser.validateDeviceName("MM-WR-A1B2C3").isSuccess)
        assertTrue(QrParser.validateDeviceName("mm-wr-ffffff").isSuccess)
        assertFalse(QrParser.validateDeviceName("INVALID-NAME").isSuccess)
        assertFalse(QrParser.validateDeviceName("MM-WR-12345").isSuccess)
        // The prefix before the firmware was renamed to a wearable (Iteration 2).
        assertFalse(QrParser.validateDeviceName("MM-GW-A1B2C3").isSuccess)
    }

    @Test
    fun testJsonPayloadExactKeysAndTypes() {
        val config = ProvisioningConfig(
            ssid = "GatewayWiFi",
            password = "example-passphrase",
            isOpenWifi = false,
            brokerHost = "192.168.1.20",
            brokerPort = 1883
        )

        val validation = config.validate()
        assertTrue("Expected valid config: ${validation.error}", validation.isValid)

        val jsonStr = config.toJsonPayload()
        val json = JSONObject(jsonStr)

        assertEquals("GatewayWiFi", json.getString("ssid"))
        assertEquals("example-passphrase", json.getString("password"))
        assertEquals("192.168.1.20", json.getString("broker_host"))
        assertEquals(1883, json.getInt("broker_port"))
    }

    @Test
    fun testOpenWifiSendsEmptyPasswordString() {
        val config = ProvisioningConfig(
            ssid = "OpenClinic",
            password = "",
            isOpenWifi = true,
            brokerHost = "10.0.0.1",
            brokerPort = 1883
        )

        val validation = config.validate()
        assertTrue("Open Wi-Fi should be valid with empty password: ${validation.error}", validation.isValid)

        val json = JSONObject(config.toJsonPayload())
        assertEquals("", json.getString("password"))
    }

    @Test
    fun testSecuredWifiPasswordLengthValidation() {
        // Password under 8 characters must fail for secured Wi-Fi
        val shortPassConfig = ProvisioningConfig(
            ssid = "ClinicSecure",
            password = "1234567",
            isOpenWifi = false,
            brokerHost = "192.168.1.1",
            brokerPort = 1883
        )
        assertFalse(shortPassConfig.validate().isValid)

        // Valid password 8-63 chars
        val validPassConfig = shortPassConfig.copy(password = "12345678")
        assertTrue(validPassConfig.validate().isValid)
    }

    @Test
    fun testBrokerHostValidation() {
        // Valid hostnames and IPv4
        val validDns = ProvisioningConfig(ssid = "Test", password = "password123", brokerHost = "mqtt.broker.local", brokerPort = 1883)
        assertTrue(validDns.validate().isValid)

        val validIpv4 = ProvisioningConfig(ssid = "Test", password = "password123", brokerHost = "192.168.1.50", brokerPort = 1883)
        assertTrue(validIpv4.validate().isValid)

        // Invalid characters (colons from IPv6, slashes, spaces)
        val invalidIpv6 = ProvisioningConfig(ssid = "Test", password = "password123", brokerHost = "fe80::1", brokerPort = 1883)
        assertFalse(invalidIpv6.validate().isValid)

        val invalidChars = ProvisioningConfig(ssid = "Test", password = "password123", brokerHost = "mqtt://broker", brokerPort = 1883)
        assertFalse(invalidChars.validate().isValid)
    }

    @Test
    fun testBrokerPortRange() {
        val configPort0 = ProvisioningConfig(ssid = "Test", password = "password123", brokerHost = "192.168.1.1", brokerPort = 0)
        assertFalse(configPort0.validate().isValid)

        val configPort65536 = ProvisioningConfig(ssid = "Test", password = "password123", brokerHost = "192.168.1.1", brokerPort = 65536)
        assertFalse(configPort65536.validate().isValid)

        val configPort1883 = ProvisioningConfig(ssid = "Test", password = "password123", brokerHost = "192.168.1.1", brokerPort = 1883)
        assertTrue(configPort1883.validate().isValid)
    }

    @Test
    fun testPayloadUnder512BytesLimit() {
        val config = ProvisioningConfig(
            ssid = "A".repeat(32),
            password = "B".repeat(63),
            isOpenWifi = false,
            brokerHost = "C".repeat(96),
            brokerPort = 65535
        )
        val validation = config.validate()
        assertTrue(validation.isValid)
        assertTrue("Max configuration must remain below 512 bytes limit", validation.byteCount <= BleConstants.MAX_PAYLOAD_BYTES)
    }
}
