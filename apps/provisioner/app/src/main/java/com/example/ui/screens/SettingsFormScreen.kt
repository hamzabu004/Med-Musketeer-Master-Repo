package com.example.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudQueue
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.example.ble.BleConstants
import com.example.model.ProvisioningConfig
import com.example.model.ValidationResult

@Composable
fun SettingsFormScreen(
    config: ProvisioningConfig,
    validation: ValidationResult,
    onConfigChange: (ssid: String?, password: String?, isOpenWifi: Boolean?, brokerHost: String?, brokerPort: Int?) -> Unit,
    onProceedToReview: () -> Unit
) {
    val scrollState = rememberScrollState()
    var isPasswordVisible by remember { mutableStateOf(false) }

    val payloadBytes = config.payloadSizeBytes()
    val isNearLimit = payloadBytes > 400
    val isOverLimit = payloadBytes > BleConstants.MAX_PAYLOAD_BYTES

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(16.dp)
    ) {
        Text(
            text = "Wearable Provisioning Settings",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground
        )

        Text(
            text = "Configure network and telemetry destinations for the ESP32-S3 wearable.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Spacer(modifier = Modifier.height(16.dp))

        // Section 1: Wi-Fi Credentials
        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface
            ),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.Wifi,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(20.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Wi-Fi Network (Wearable Internet Access)",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }

                Spacer(modifier = Modifier.height(12.dp))

                // SSID
                OutlinedTextField(
                    value = config.ssid,
                    onValueChange = { onConfigChange(it, null, null, null, null) },
                    label = { Text("Wi-Fi SSID (1–32 characters)") },
                    placeholder = { Text("MyClinicNetwork") },
                    singleLine = true,
                    isError = validation.field == "ssid",
                    supportingText = {
                        Text(
                            text = if (validation.field == "ssid") validation.error ?: "" else "${config.ssid.length}/32 characters",
                            color = if (validation.field == "ssid") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("wifi_ssid_input")
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Open Network Checkbox
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp)
                ) {
                    Checkbox(
                        checked = config.isOpenWifi,
                        onCheckedChange = { isOpen ->
                            onConfigChange(null, if (isOpen) "" else config.password, isOpen, null, null)
                        },
                        colors = CheckboxDefaults.colors(checkedColor = MaterialTheme.colorScheme.primary),
                        modifier = Modifier.testTag("open_wifi_checkbox")
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Column {
                        Text(
                            text = "Open Network (No Password)",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        Text(
                            text = "Sends empty password string \"\" to firmware",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                // Wi-Fi Password
                OutlinedTextField(
                    value = config.password,
                    onValueChange = { onConfigChange(null, it, null, null, null) },
                    label = { Text("Wi-Fi Password (8–63 characters)") },
                    placeholder = { Text("WPA2/WPA3 passphrase") },
                    singleLine = true,
                    enabled = !config.isOpenWifi,
                    isError = validation.field == "password",
                    visualTransformation = if (isPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    trailingIcon = {
                        if (!config.isOpenWifi) {
                            IconButton(
                                onClick = { isPasswordVisible = !isPasswordVisible },
                                modifier = Modifier.testTag("toggle_password_visibility")
                            ) {
                                Icon(
                                    imageVector = if (isPasswordVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                                    contentDescription = if (isPasswordVisible) "Hide password" else "Show password"
                                )
                            }
                        }
                    },
                    supportingText = {
                        Text(
                            text = if (config.isOpenWifi) "Password disabled for open network"
                            else if (validation.field == "password") validation.error ?: ""
                            else "${config.password.length}/63 characters (min 8)",
                            color = if (validation.field == "password") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("wifi_password_input")
                )
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Section 2: MQTT Broker Settings
        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface
            ),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.CloudQueue,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(20.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "MQTT Broker (Telemetry Destination)",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }

                Spacer(modifier = Modifier.height(4.dp))

                Text(
                    text = "Separate from your Wi-Fi network. The wearable publishes sensor readings to this broker at mqtt://<host>:<port>.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Broker Host
                OutlinedTextField(
                    value = config.brokerHost,
                    onValueChange = { onConfigChange(null, null, null, it, null) },
                    label = { Text("Broker Host / IPv4 (1–96 characters)") },
                    placeholder = { Text("192.168.1.20 or mqtt.local") },
                    singleLine = true,
                    isError = validation.field == "brokerHost",
                    supportingText = {
                        Text(
                            text = if (validation.field == "brokerHost") validation.error ?: ""
                            else "Only ASCII letters, digits, dots, hyphens (IPv6 not supported)",
                            color = if (validation.field == "brokerHost") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("broker_host_input")
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Broker Port
                OutlinedTextField(
                    value = if (config.brokerPort == 0) "" else config.brokerPort.toString(),
                    onValueChange = { text ->
                        val portInt = text.filter { it.isDigit() }.toIntOrNull() ?: 0
                        onConfigChange(null, null, null, null, portInt)
                    },
                    label = { Text("Broker Port (1–65535, default 1883)") },
                    placeholder = { Text("1883") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    isError = validation.field == "brokerPort",
                    supportingText = {
                        Text(
                            text = if (validation.field == "brokerPort") validation.error ?: "" else "Standard unencrypted MQTT uses 1883",
                            color = if (validation.field == "brokerPort") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("broker_port_input")
                )
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Payload Budget Tracker Card
        Card(
            shape = RoundedCornerShape(12.dp),
            colors = CardDefaults.cardColors(
                containerColor = when {
                    isOverLimit -> MaterialTheme.colorScheme.errorContainer
                    isNearLimit -> MaterialTheme.colorScheme.tertiary.copy(alpha = 0.15f)
                    else -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                }
            ),
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = if (isOverLimit) Icons.Default.Warning else Icons.Default.Info,
                    contentDescription = null,
                    tint = if (isOverLimit) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(20.dp)
                )
                Spacer(modifier = Modifier.width(10.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Firmware JSON Payload Size: $payloadBytes / 511 bytes",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (isOverLimit) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        text = if (isOverLimit) "Exceeds 511-byte limit! Shorten SSID or host." else "Within ESP32-S3 firmware buffer limit.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        Button(
            onClick = onProceedToReview,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp)
                .testTag("proceed_to_review_button")
        ) {
            Text("Review & Send Settings", fontWeight = FontWeight.Bold)
        }

        Spacer(modifier = Modifier.height(16.dp))
    }
}
