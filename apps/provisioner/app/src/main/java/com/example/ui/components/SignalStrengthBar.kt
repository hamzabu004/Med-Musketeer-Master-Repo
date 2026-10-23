package com.example.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable
fun SignalStrengthBar(
    rssi: Int,
    modifier: Modifier = Modifier
) {
    // RSSI typically ranges from -100 (very weak) to -40 (very strong)
    val level = when {
        rssi >= -60 -> 4
        rssi >= -75 -> 3
        rssi >= -85 -> 2
        else -> 1
    }

    val activeColor = when (level) {
        4 -> MaterialTheme.colorScheme.secondary
        3 -> MaterialTheme.colorScheme.primary
        2 -> MaterialTheme.colorScheme.tertiary
        else -> MaterialTheme.colorScheme.error
    }

    val inactiveColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f)

    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.Bottom
    ) {
        Bar(height = 6, color = if (level >= 1) activeColor else inactiveColor)
        Bar(height = 10, color = if (level >= 2) activeColor else inactiveColor)
        Bar(height = 14, color = if (level >= 3) activeColor else inactiveColor)
        Bar(height = 18, color = if (level >= 4) activeColor else inactiveColor)
    }
}

@Composable
private fun Bar(height: Int, color: Color) {
    Box(
        modifier = Modifier
            .width(3.dp)
            .height(height.dp)
            .clip(RoundedCornerShape(1.dp))
            .background(color)
    )
}
