package com.example.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

data class ChecklistItem(
    val title: String,
    val expectedOutcome: String,
    val procedure: String
)

val TEST_CHECKLIST_ITEMS = listOf(
    ChecklistItem(
        title = "1. Malformed QR Payload",
        procedure = "Scan arbitrary text or QR without pipe separator, or with wrong service UUID.",
        expectedOutcome = "App rejects with clear error dialog without starting BLE scan."
    ),
    ChecklistItem(
        title = "2. Permissions Denied",
        procedure = "Deny Bluetooth or Camera runtime permission in system dialog.",
        expectedOutcome = "App shows informative rationale banner and fallback manual entry button."
    ),
    ChecklistItem(
        title = "3. No Device Found / Timeout",
        procedure = "Scan for an offline wearable name or with ESP32 turned off.",
        expectedOutcome = "BLE scan active timeout triggers after 15s with Retry Scan control."
    ),
    ChecklistItem(
        title = "4. Pairing Rejected / Passkey Error",
        procedure = "Dismiss the Android system passkey prompt or enter wrong passkey.",
        expectedOutcome = "Bonding failure is caught; app alerts user to retry and check wearable OLED."
    ),
    ChecklistItem(
        title = "5. Wrong Service / Characteristic",
        procedure = "Connect to an incompatible BLE device missing 7a2e0001 service.",
        expectedOutcome = "GATT service discovery flags missing UUID and disconnects safely."
    ),
    ChecklistItem(
        title = "6. Open Wi-Fi Network",
        procedure = "Check 'Open Wi-Fi Network' toggle in the configuration form.",
        expectedOutcome = "Password field is disabled and JSON payload sends password as empty string: \"\"."
    ),
    ChecklistItem(
        title = "7. Invalid Broker Host / Port",
        procedure = "Enter an IPv6 address, port 0, port 70000, or invalid symbols.",
        expectedOutcome = "Inline field validation blocks submission with descriptive constraint error."
    ),
    ChecklistItem(
        title = "8. Payload Size Limit (>512 bytes)",
        procedure = "Fill fields with long allowed strings nearing maximum limits.",
        expectedOutcome = "Live byte counter warns user if total UTF-8 bytes reach or exceed 512."
    ),
    ChecklistItem(
        title = "9. Successful GATT Write",
        procedure = "Complete bonded write with valid parameters.",
        expectedOutcome = "GATT write with response returns SUCCESS; app displays confirmation noting OLED is source of truth."
    ),
    ChecklistItem(
        title = "10. OLED Display Scan & Anti-Flicker",
        procedure = "Scan OLED with PWM refresh flicker, inverted colors, or high glare.",
        expectedOutcome = "Multi-pass analyzer (inverted + global histogram), tap-to-focus ring, zoom controls (1.5x/2x), and anti-glare mode achieve fast lock."
    )
)

@Composable
fun TestChecklistDialog(
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = "Manual Test Checklist",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f)
                )
                IconButton(onClick = onDismiss) {
                    Icon(imageVector = Icons.Default.Close, contentDescription = "Close")
                }
            }
        },
        text = {
            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag("test_checklist_list")
            ) {
                item {
                    Text(
                        text = "Use this verification guide to test edge cases on real hardware or in QA:",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(bottom = 12.dp)
                    )
                }
                items(TEST_CHECKLIST_ITEMS) { item ->
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                        ),
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp)
                    ) {
                        Column(modifier = Modifier.padding(10.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    modifier = Modifier
                                        .size(18.dp)
                                        .clip(CircleShape)
                                        .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.2f)),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Check,
                                        contentDescription = null,
                                        tint = MaterialTheme.colorScheme.primary,
                                        modifier = Modifier.size(12.dp)
                                    )
                                }
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = item.title,
                                    style = MaterialTheme.typography.labelLarge,
                                    fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.onSurface
                                )
                            }
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "Test: ${item.procedure}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = "Expected: ${item.expectedOutcome}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.primary,
                                fontWeight = FontWeight.Medium
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text("Dismiss")
            }
        }
    )
}
